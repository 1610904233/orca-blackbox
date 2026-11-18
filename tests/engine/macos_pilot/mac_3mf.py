"""Minimal 3MF project geometry reader for the macOS pilots.

The app writes one root ``3D/3dmodel.model`` with:

* ``<object id=N type="model">`` containers whose ``<component p:path=...>``
  entries point at external ``3D/Objects/*.model`` meshes;
* one ``<item objectid=N transform="...">`` per placed object in ``<build>``;
* ``Metadata/model_settings.config`` with the user-visible object names.

Only what the ports need is implemented: object names, component paths,
12-number 3x4 transforms (row-major 3x3 + translation), mesh vertices and
axis-aligned bounds.  Pure stdlib.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Transform",
    "Component",
    "ProjectObject",
    "ProjectGeometry",
    "read_project",
    "read_mesh_vertices",
    "object_names",
    "read_plates",
    "read_plates_detailed",
    "plate_names",
    "object_world_aabbs",
    "object_aabbs_by_id",
    "local_aabb",
    "apply_transform",
    "compose",
    "world_aabb",
]

Transform = tuple[float, ...]  # 12 numbers: m00..m22, tx, ty, tz
IDENTITY: Transform = (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)


@dataclass
class Component:
    path: str
    transform: Transform = IDENTITY


@dataclass
class ProjectObject:
    id: str
    name: str = ""
    components: list[Component] = field(default_factory=list)


@dataclass
class ProjectGeometry:
    objects: list[ProjectObject] = field(default_factory=list)
    #: build-item transforms in document order (one per placed object)
    items: list[tuple[str, Transform]] = field(default_factory=list)


def _parse_transform(text: str | None) -> Transform:
    if not text:
        return IDENTITY
    values = tuple(float(v) for v in text.split())
    return values if len(values) == 12 else IDENTITY


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_project(path: Path | str) -> ProjectGeometry:
    """Objects + build-item transforms from a saved .3mf."""
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        root = z.read("3D/3dmodel.model").decode("utf-8", "replace")
        names = _object_names(z)
    geo = ProjectGeometry()

    # Root objects and their components (regex keeps namespace handling simple;
    # the app's XML is machine-written and stable).
    for match in re.finditer(
            r'<object\s+id="(\d+)"[^>]*>(.*?)</object>', root, re.S):
        oid, body = match.group(1), match.group(2)
        obj = ProjectObject(id=oid, name=names.get(oid, ""))
        for comp in re.finditer(r"<component\s+([^>]*)/>", body):
            attrs = comp.group(1)
            pm = re.search(r'p:path="([^"]*)"', attrs)
            tm = re.search(r'transform="([^"]*)"', attrs)
            obj.components.append(Component(
                path=pm.group(1) if pm else "",
                transform=_parse_transform(tm.group(1) if tm else None)))
        geo.objects.append(obj)

    for item in re.finditer(r"<item\s+([^>]*)/>", root):
        attrs = item.group(1)
        om = re.search(r'objectid="(\d+)"', attrs)
        tm = re.search(r'transform="([^"]*)"', attrs)
        if om:
            geo.items.append((om.group(1),
                              _parse_transform(tm.group(1) if tm else None)))
    return geo


def _object_names(z: zipfile.ZipFile) -> dict[str, str]:
    try:
        text = z.read("Metadata/model_settings.config").decode(
            "utf-8", "replace")
    except KeyError:
        return {}
    return _names_from_text(text)


def _names_from_text(text: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for match in re.finditer(
            r'<object\s+id="(\d+)"[^>]*>(.*?)</object>', text, re.S):
        nm = re.search(r'key="name"\s+value="([^"]*)"', match.group(2))
        if nm:
            names[match.group(1)] = nm.group(1)
    return names


def read_plates(path: Path | str) -> dict[str, list[str]]:
    """plate id -> object names on that plate (model_settings.config)."""
    return {pid: [name for _oid, name in items]
            for pid, items in read_plates_detailed(path).items()}


def object_names(path: Path | str) -> list[str]:
    """User-visible object names in document order (model_settings)."""
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        try:
            text = z.read("Metadata/model_settings.config").decode(
                "utf-8", "replace")
        except KeyError:
            return []
    names = _names_from_text(text)
    # keep document order of <object id=...> blocks
    order = re.findall(r'<object\s+id="(\d+)"', text)
    out = []
    seen = set()
    for oid in order:
        if oid in seen:
            continue
        seen.add(oid)
        out.append(names.get(oid, oid))
    return out


def plate_names(path: Path | str) -> list[str]:
    """plater_name values in document order."""
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        try:
            text = z.read("Metadata/model_settings.config").decode(
                "utf-8", "replace")
        except KeyError:
            return []
    return re.findall(r'key="plater_name"\s+value="([^"]*)"', text)


def plate_locked(path: Path | str) -> dict[str, bool]:
    """plate id -> locked flag (``key="locked"`` in model_settings.config)."""
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        try:
            text = z.read("Metadata/model_settings.config").decode(
                "utf-8", "replace")
        except KeyError:
            return {}
    out: dict[str, bool] = {}
    for match in re.finditer(r"<plate>(.*?)</plate>", text, re.S):
        body = match.group(1)
        pid = re.search(r'plater_id"\s+value="(\d+)"', body)
        locked = re.search(r'key="locked"\s+value="(true|false)"', body)
        if pid and locked:
            out[pid.group(1)] = locked.group(1) == "true"
    return out


def read_plates_detailed(path: Path | str) -> dict[str, list[tuple[str, str]]]:
    """plate id -> [(object id, object name)] in model_settings.config."""
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        try:
            text = z.read("Metadata/model_settings.config").decode(
                "utf-8", "replace")
        except KeyError:
            return {}
    names = _names_from_text(text)
    plates: dict[str, list[tuple[str, str]]] = {}
    for match in re.finditer(r"<plate>(.*?)</plate>", text, re.S):
        body = match.group(1)
        pid = re.search(r'plater_id"\s+value="(\d+)"', body)
        if not pid:
            continue
        ids = re.findall(r'key="object_id"\s+value="(\d+)"', body)
        plates[pid.group(1)] = [(i, names.get(i, i)) for i in ids]
    return plates


def read_mesh_vertices(path: Path | str, member: str) -> list[tuple[float, float, float]]:
    """Vertices from an external model file inside the project zip."""
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        text = z.read(member.lstrip("/")).decode("utf-8", "replace")
    return [(float(x), float(y), float(z_))
            for x, y, z_ in re.findall(
                r'<vertex\s+x="([^"]+)"\s+y="([^"]+)"\s+z="([^"]+)"', text)]


def local_aabb(vertices: list[tuple[float, float, float]]):
    if not vertices:
        return None
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def apply_transform(transform: Transform,
                    point: tuple[float, float, float]):
    x, y, z = point
    m = transform
    return (m[0] * x + m[1] * y + m[2] * z + m[9],
            m[3] * x + m[4] * y + m[5] * z + m[10],
            m[6] * x + m[7] * y + m[8] * z + m[11])


def compose(outer: Transform, inner: Transform) -> Transform:
    """outer ∘ inner (apply inner first, then outer)."""
    a, b = outer, inner
    r = [
        a[0] * b[0] + a[1] * b[3] + a[2] * b[6],
        a[0] * b[1] + a[1] * b[4] + a[2] * b[7],
        a[0] * b[2] + a[1] * b[5] + a[2] * b[8],
        a[3] * b[0] + a[4] * b[3] + a[5] * b[6],
        a[3] * b[1] + a[4] * b[4] + a[5] * b[7],
        a[3] * b[2] + a[4] * b[5] + a[5] * b[8],
        a[6] * b[0] + a[7] * b[3] + a[8] * b[6],
        a[6] * b[1] + a[7] * b[4] + a[8] * b[7],
        a[6] * b[2] + a[7] * b[5] + a[8] * b[8],
    ]
    tx, ty, tz = apply_transform(a, (b[9], b[10], b[11]))
    return tuple(r) + (tx, ty, tz)


def world_aabb(vertices, transform: Transform):
    if not vertices:
        return None
    pts = [apply_transform(transform, v) for v in vertices]
    return local_aabb(pts)


def object_aabbs_by_id(path: Path | str) -> dict[str, tuple]:
    """object id -> (name, world AABB union over its components)."""
    path = Path(path)
    geo = read_project(path)
    items = dict(geo.items)
    cache: dict[str, list] = {}
    out: dict[str, tuple] = {}
    for obj in geo.objects:
        item_t = items.get(obj.id, IDENTITY)
        lo = [1e18, 1e18, 1e18]
        hi = [-1e18, -1e18, -1e18]
        for comp in obj.components:
            if comp.path not in cache:
                try:
                    cache[comp.path] = read_mesh_vertices(path, comp.path)
                except KeyError:
                    cache[comp.path] = []
            bounds = world_aabb(cache[comp.path],
                                compose(item_t, comp.transform))
            if not bounds:
                continue
            for i in range(3):
                lo[i] = min(lo[i], bounds[0][i])
                hi[i] = max(hi[i], bounds[1][i])
        if hi[0] > lo[0] or hi[1] > lo[1] or hi[2] > lo[2]:
            out[obj.id] = (obj.name or obj.id, (tuple(lo), tuple(hi)))
    return out


def object_world_aabbs(path: Path | str) -> dict[str, tuple]:
    """object name -> world-space AABB (union over its components)."""
    return {name: bounds
            for name, bounds in object_aabbs_by_id(path).values()}

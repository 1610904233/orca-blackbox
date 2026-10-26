import zipfile, hashlib, re, os
base = r'C:\coil\orca-blackbox\artifacts'
out = []
for n in ('m8x_202_a.3mf', 'm8x_202_b.3mf'):
    p = os.path.join(base, n)
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        model = z.read('3D/3dmodel.model') if '3D/3dmodel.model' in names else b''
        objs = len(re.findall(rb'<object\b', model))
        verts = len(re.findall(rb'<vertex\b', model))
        builds = len(re.findall(rb'<item\b', model))
        out.append(f'{n}: parts={len(names)} objects={objs} items={builds} verts={verts} '
                   f'model_md5={hashlib.md5(model).hexdigest()[:12]}')
print('\n'.join(out))

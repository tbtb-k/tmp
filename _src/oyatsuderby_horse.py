# おやつダービー：デフォルメ馬をBlenderで作る（Blender 5.x / bpy）
# 座標：X=横、Y=うしろ（馬は -Y を向く）、Z=上。単位はメートル
#
# 作りなおすとき：
#   pip install bpy==5.2.2
#   python oyatsuderby_horse.py -- export            … このフォルダに oyatsuderby_horse.glb ができる
#   python oyatsuderby_horse.py -- preview v1        … 形の確認用の画像（横・前・後ろ）
#   python oyatsuderby_horse.py -- poses p1          … 走るポーズの確認用の画像
# できた oyatsuderby_horse.glb を、ゲーム（game_20261012_oyatsuderby.html）と同じ場所に置く。
# 色の名前（Coat・Mane・Muzzle・Silk・Cloth など）はゲーム側が毛色・勝負服・ゼッケンにぬりかえるので、変えないこと。
import bpy, bmesh, math, sys, os
from mathutils import Vector, Matrix, Euler

OUT = os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------- 材質（名前でゲーム側が色をつけかえる） ----------
def mat(name, rgb, rough=0.6, spec=0.3):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    return m

def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple((x/12.92) if x <= 0.04045 else ((x+0.055)/1.055)**2.4 for x in c)

M = {
    "Coat":   mat("Coat",   srgb("#b0612c"), 0.55),
    "Muzzle": mat("Muzzle", srgb("#e7b48a"), 0.6),
    "Mane":   mat("Mane",   srgb("#5a2e14"), 0.7),
    "Hoof":   mat("Hoof",   srgb("#3a2a22"), 0.4),
    "Eye":    mat("Eye",    srgb("#1d1410"), 0.15),
    "EyeHi":  mat("EyeHi",  srgb("#ffffff"), 0.2),
    "Blush":  mat("Blush",  srgb("#ff9fae"), 0.7),
    "Silk":   mat("Silk",   srgb("#e53935"), 0.35),
    "Skin":   mat("Skin",   srgb("#f6d2b4"), 0.6),
    "Pants":  mat("Pants",  srgb("#f6f6f2"), 0.6),
    "Boots":  mat("Boots",  srgb("#222222"), 0.35),
    "Saddle": mat("Saddle", srgb("#4a3020"), 0.5),
    "Cloth":  mat("Cloth",  srgb("#ffffff"), 0.6),
}

PARTS = []   # (object, bone or None, weight-mode)

def link(obj):
    scene.collection.objects.link(obj)
    return obj

def apply_all(obj):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)

def skin_chain(name, pts, radii, material, sub=2, smooth=True, dec=0.35):
    """点の列（とその太さ）から、なめらかな筒をつくる"""
    me = bpy.data.meshes.new(name)
    edges = [(i, i+1) for i in range(len(pts)-1)]
    me.from_pydata([Vector(p) for p in pts], edges, [])
    obj = link(bpy.data.objects.new(name, me))
    obj.modifiers.new("skin", 'SKIN')
    sv = me.skin_vertices[0].data
    for i, r in enumerate(radii):
        sv[i].radius = r if isinstance(r, tuple) else (r, r)
    sv[0].use_root = True
    s = obj.modifiers.new("sub", 'SUBSURF'); s.levels = sub; s.render_levels = sub
    if dec and dec < 1:
        d = obj.modifiers.new("dec", 'DECIMATE'); d.ratio = dec   # スマホでも軽く動くように面を減らす
    apply_all(obj)
    if smooth:
        for p in obj.data.polygons: p.use_smooth = True
    obj.data.materials.append(M[material])
    return obj

def blob(name, loc, scale, material, rot=(0, 0, 0), seg=None, ring=None):
    big = max(scale)
    if seg is None: seg, ring = (28, 18) if big > 0.3 else (18, 12) if big > 0.1 else (12, 8)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    obj = link(bpy.data.objects.new(name, me))
    for p in obj.data.polygons: p.use_smooth = True
    obj.scale = scale; obj.rotation_euler = rot; obj.location = loc
    obj.data.materials.append(M[material])
    bake_transform(obj)
    return obj

def cone(name, loc, r1, r2, depth, material, rot=(0, 0, 0), verts=16):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r1, radius2=r2, depth=depth)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    obj = link(bpy.data.objects.new(name, me))
    for p in obj.data.polygons: p.use_smooth = True
    obj.rotation_euler = rot; obj.location = loc
    obj.data.materials.append(M[material])
    bake_transform(obj)
    return obj

def bake_transform(obj):
    obj.data.transform(obj.matrix_basis)
    obj.matrix_basis = Matrix.Identity(4)

# ---------- 体・首（ひとつながり）と、まるい大きな頭 ----------
HC = Vector((0, -0.86, 1.72))   # 頭の中心
HR = 0.42                        # 頭の大きさ（大きめでかわいく）
body = skin_chain("Body",
    [(0, 0.5, 0.95), (0, 0.05, 0.92), (0, -0.38, 0.98), (0, -0.58, 1.22), (0, -0.72, 1.5)],
    [(0.37, 0.38), (0.42, 0.42), (0.4, 0.41), (0.27, 0.28), (0.25, 0.25)],
    "Coat")
PARTS.append((body, None, "body"))
PARTS.append((blob("Head", tuple(HC), (HR*0.95, HR, HR*0.93), "Coat"), "head", "rigid"))

def on_head(dx, dy, dz, out=0.0):
    d = Vector((dx, dy, dz)).normalized()
    return tuple(HC + Vector((d.x*HR*0.95, d.y*HR, d.z*HR*0.93))*(1+out/HR))

# 鼻先（色がちょっと明るい）と鼻の穴・ほっぺ・目・耳・前髪
PARTS.append((blob("Muzzle", (0, -1.2, 1.57), (0.26, 0.2, 0.2), "Muzzle"), "head", "rigid"))
for sx in (1, -1):
    PARTS.append((blob("Nostril", (sx*0.1, -1.39, 1.61), (0.032, 0.02, 0.026), "Eye"), "head", "rigid"))
    PARTS.append((blob("Eye", on_head(sx*0.72, -0.62, 0.2, -0.03), (0.05, 0.1, 0.12), "Eye", rot=(0, 0, sx*0.8)), "head", "rigid"))
    PARTS.append((blob("EyeHi", on_head(sx*0.68, -0.66, 0.31, -0.002), (0.016, 0.03, 0.036), "EyeHi", rot=(0, 0, sx*0.8)), "head", "rigid"))
    PARTS.append((blob("Blush", on_head(sx*0.66, -0.72, -0.22, -0.015), (0.025, 0.07, 0.045), "Blush", rot=(0, 0, sx*0.85)), "head", "rigid"))
    PARTS.append((cone("Ear", (sx*0.19, -0.74, 2.1), 0.09, 0.0, 0.23, "Coat", rot=(-0.15, sx*0.36, 0)), "head", "rigid"))
PARTS.append((blob("Forelock", (0, -1.07, 2.03), (0.12, 0.11, 0.075), "Mane", rot=(0.75, 0, 0)), "head", "rigid"))
# たてがみ：首のうしろにふわふわを並べる
for i, (y, z, r) in enumerate(((-0.74, 2.09, 0.11), (-0.62, 1.94, 0.115), (-0.56, 1.74, 0.11), (-0.5, 1.54, 0.1), (-0.43, 1.36, 0.08))):
    PARTS.append((blob("Mane", (0, y, z), (r*0.62, r*1.1, r), "Mane", rot=(0.6, 0, 0)), "head" if i == 0 else "neck", "rigid"))

# ---------- しっぽ（ふさふさ） ----------
tail = skin_chain("Tail",
    [(0, 0.6, 1.08), (0, 0.8, 1.02), (0, 0.95, 0.8), (0, 1.0, 0.56)],
    [0.11, 0.15, 0.14, 0.07], "Mane")
PARTS.append((tail, None, "tail"))

# ---------- 脚（前2本・後2本。短めで太め） ----------
for side, sx in (("L", 1), ("R", -1)):
    f = skin_chain("Leg_F"+side,
        [(sx*0.19, -0.36, 0.86), (sx*0.19, -0.38, 0.45), (sx*0.19, -0.39, 0.19), (sx*0.19, -0.4, 0.12)],
        [0.15, 0.105, 0.09, 0.095], "Coat")
    h = skin_chain("Leg_H"+side,
        [(sx*0.2, 0.38, 0.88), (sx*0.2, 0.47, 0.45), (sx*0.2, 0.44, 0.19), (sx*0.2, 0.43, 0.12)],
        [0.19, 0.11, 0.09, 0.095], "Coat")
    PARTS.append((f, "F"+side, "leg"))
    PARTS.append((h, "H"+side, "leg"))
    PARTS.append((cone("Hoof", (sx*0.19, -0.4, 0.065), 0.115, 0.1, 0.13, "Hoof"), "lo_F"+side, "rigid"))
    PARTS.append((cone("Hoof", (sx*0.2, 0.43, 0.065), 0.115, 0.1, 0.13, "Hoof"), "lo_H"+side, "rigid"))

# ---------- 鞍・ゼッケン（番号の布） ----------
PARTS.append((blob("Saddle", (0, 0.0, 1.33), (0.3, 0.28, 0.06), "Saddle"), "body", "rigid"))
def cloth(side):
    """胴の横に沿って曲がった布。外から見て番号が正しく読めるように UV を貼る"""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    y0, y1, a0, a1, nu, nv = -0.26, 0.28, 0.45, 1.5, 6, 6
    grid = []
    for j in range(nv+1):
        row = []
        a = a0 + (a1-a0)*j/nv
        for i in range(nu+1):
            y = y0 + (y1-y0)*i/nu
            rr = 0.445 + 0.012*math.cos((i/nu-0.5)*math.pi)
            row.append(bm.verts.new((side*rr*math.sin(a), y, 0.93 + rr*math.cos(a))))
        grid.append(row)
    for j in range(nv):
        for i in range(nu):
            vs = [grid[j][i], grid[j][i+1], grid[j+1][i+1], grid[j+1][i]]
            if side > 0: vs = vs[::-1]          # 面の向きを外側にそろえる
            f = bm.faces.new(vs)
            for l in f.loops:
                jj = [r for r in range(nv+1) if l.vert in grid[r]][0]
                ii = grid[jj].index(l.vert)
                u = ii/nu if side > 0 else 1-ii/nu   # 外から見て文字が左右反転しないように
                l[uv].uv = (u, 1-jj/nv)
    me = bpy.data.meshes.new("Cloth"); bm.to_mesh(me); bm.free()
    obj = link(bpy.data.objects.new("Cloth", me))
    for p in obj.data.polygons: p.use_smooth = True
    obj.data.materials.append(M["Cloth"])
    return obj
for sx in (1, -1): PARTS.append((cloth(sx), "body", "rigid"))

# ---------- 騎手（頭の大きいちびキャラ） ----------
J = []
J.append(blob("J_Torso", (0, 0.05, 1.59), (0.165, 0.2, 0.17), "Silk", rot=(0.5, 0, 0)))
J.append(blob("J_Head", (0, -0.15, 1.85), (0.2, 0.2, 0.2), "Skin"))
J.append(blob("J_Helmet", (0, -0.14, 1.92), (0.215, 0.22, 0.175), "Silk"))
J.append(blob("J_Visor", (0, -0.35, 1.88), (0.15, 0.06, 0.03), "Silk", rot=(0.35, 0, 0)))
for sx in (1, -1):
    J.append(blob("J_Eye", (sx*0.07, -0.34, 1.82), (0.02, 0.014, 0.03), "Eye"))
    J.append(skin_chain("J_Arm", [(sx*0.15, -0.02, 1.67), (sx*0.15, -0.22, 1.57), (sx*0.1, -0.42, 1.49)], [0.055, 0.05, 0.045], "Silk", sub=1))
    J.append(blob("J_Hand", (sx*0.1, -0.44, 1.48), (0.048, 0.048, 0.048), "Skin"))
    J.append(skin_chain("J_Leg", [(sx*0.14, 0.08, 1.45), (sx*0.25, -0.12, 1.38), (sx*0.25, -0.02, 1.21)], [0.075, 0.065, 0.055], "Pants", sub=1))
    J.append(blob("J_Boot", (sx*0.25, -0.04, 1.18), (0.055, 0.09, 0.065), "Boots"))
for j in J: PARTS.append((j, "jockey", "rigid"))

# ---------- 骨（アーマチュア） ----------
BONES = {   # 名前: (根元, 先, 親)
    "root":  ((0, 0, 0), (0, 0, 0.25), None),
    "body":  ((0, 0.5, 0.95), (0, -0.4, 0.98), "root"),
    "neck":  ((0, -0.5, 1.12), (0, -0.72, 1.5), "body"),
    "head":  ((0, -0.72, 1.5), (0, -1.2, 1.6), "neck"),
    "tail1": ((0, 0.62, 1.08), (0, 0.88, 0.95), "body"),
    "tail2": ((0, 0.88, 0.95), (0, 1.0, 0.54), "tail1"),
    "jockey":((0, 0.04, 1.3), (0, 0.04, 1.65), "body"),
}
for side, sx in (("L", 1), ("R", -1)):
    BONES["up_F"+side] = ((sx*0.19, -0.36, 0.86), (sx*0.19, -0.38, 0.45), "body")
    BONES["lo_F"+side] = ((sx*0.19, -0.38, 0.45), (sx*0.19, -0.4, 0.06), "up_F"+side)
    BONES["up_H"+side] = ((sx*0.2, 0.38, 0.88), (sx*0.2, 0.47, 0.45), "body")
    BONES["lo_H"+side] = ((sx*0.2, 0.47, 0.45), (sx*0.2, 0.43, 0.06), "up_H"+side)

arm = bpy.data.armatures.new("Rig")
rig = link(bpy.data.objects.new("Rig", arm))
bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.objects.active = rig; rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
for n, (h, t, p) in BONES.items():
    eb = arm.edit_bones.new(n); eb.head = h; eb.tail = t; eb.roll = 0
for n, (h, t, p) in BONES.items():
    if p:
        eb = arm.edit_bones[n]; eb.parent = arm.edit_bones[p]
        eb.use_connect = False
bpy.ops.object.mode_set(mode='OBJECT')

def seg_dist(p, a, b):
    a, b = Vector(a), Vector(b); ab = b-a
    t = max(0.0, min(1.0, (p-a).dot(ab)/ab.length_squared))
    return (p-(a+ab*t)).length

def blend_weights(obj, names, top_only=None):
    gs = {n: obj.vertex_groups.new(name=n) for n in names}
    for v in obj.data.vertices:
        ws = []
        for n in names:
            d = seg_dist(v.co, BONES[n][0], BONES[n][1])
            ws.append((n, 1.0/(d**4+1e-4)))
        if top_only and v.co.z > top_only[1]:
            ws = [(top_only[0], 1.0)]
        tot = sum(w for _, w in ws)
        for n, w in ws:
            if w/tot > 0.01: gs[n].add([v.index], w/tot, 'REPLACE')

for obj, bone, mode in PARTS:
    if mode == "rigid":
        g = obj.vertex_groups.new(name=bone)
        g.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')
    elif mode == "body":
        blend_weights(obj, ["body", "neck"])
    elif mode == "tail":
        blend_weights(obj, ["tail1", "tail2"])
    elif mode == "leg":
        top = BONES["up_"+bone][0][2]
        blend_weights(obj, ["up_"+bone, "lo_"+bone], top_only=("up_"+bone, top-0.12))

# ひとつのメッシュにまとめて、骨で動くようにする
bpy.ops.object.select_all(action='DESELECT')
objs = [o for o, _, _ in PARTS]
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.join()
horse = bpy.context.object; horse.name = "Horse"; horse.data.name = "Horse"
horse.parent = rig
md = horse.modifiers.new("Armature", 'ARMATURE'); md.object = rig
print("TRIS", sum(len(p.vertices)-2 for p in horse.data.polygons), "VERTS", len(horse.data.vertices))

# ---------- 動き（ギャロップ／立ち止まり） ----------
TAU = math.pi*2
for pb in rig.pose.bones: pb.rotation_mode = 'XYZ'
def key_action(name, frames, fn):
    act = bpy.data.actions.new(name); act.use_fake_user = True
    rig.animation_data_create(); rig.animation_data.action = act
    for f in range(frames+1):
        p = (f % frames)/frames
        for pb in rig.pose.bones:
            pb.rotation_euler = (0, 0, 0); pb.location = (0, 0, 0)
        fn(p)
        for pb in rig.pose.bones:
            pb.keyframe_insert("rotation_euler", frame=f)
            pb.keyframe_insert("location", frame=f)
    return act

LEG_OFF = {"HL": 0.0, "HR": 0.1, "FL": 0.52, "FR": 0.62}
def gallop(p):
    P = rig.pose.bones
    for k, off in LEG_OFF.items():
        a = TAU*(p+off); front = k[0] == "F"
        P["up_"+k].rotation_euler.x = (0.62 if front else 0.55)*math.sin(a)
        if front: P["lo_"+k].rotation_euler.x = -1.1*max(0.0, math.sin(a+1.3))
        else:     P["lo_"+k].rotation_euler.x = 0.8*max(0.0, math.sin(a-0.5))
    bob = 0.07*math.sin(TAU*p+0.6)
    P["root"].location.y = bob
    P["body"].rotation_euler.x = 0.06*math.sin(TAU*p+1.6)
    P["neck"].rotation_euler.x = 0.14*math.sin(TAU*p+2.6)
    P["head"].rotation_euler.x = -0.08*math.sin(TAU*p+2.6)
    P["tail1"].rotation_euler.x = 0.3+0.07*math.sin(TAU*p)
    P["tail2"].rotation_euler.x = 0.2+0.18*math.sin(TAU*p+1.2)
    P["jockey"].location.y = -0.7*bob
    P["jockey"].rotation_euler.x = -0.04*math.sin(TAU*p+1.6)
def idle(p):
    P = rig.pose.bones
    P["root"].location.y = 0.008*math.sin(TAU*p)
    P["neck"].rotation_euler.x = 0.05*math.sin(TAU*p)
    P["head"].rotation_euler.x = 0.04*math.sin(TAU*2*p+0.5)
    P["tail1"].rotation_euler.x = 0.1
    P["tail2"].rotation_euler.z = 0.3*math.sin(TAU*p)
    P["jockey"].location.y = 0.006*math.sin(TAU*p+0.8)
A_GALLOP = key_action("Gallop", 24, gallop)
A_IDLE = key_action("Idle", 48, idle)
rig.animation_data.action = A_IDLE
for pb in rig.pose.bones: pb.rotation_euler = (0, 0, 0); pb.location = (0, 0, 0)

def export(path):
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True); horse.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True,
        export_animations=True, export_animation_mode='ACTIONS', export_skins=True,
        export_morph=False, export_lights=False, export_cameras=False,
        export_texcoords=True, export_normals=True, export_tangents=False,
        export_materials='EXPORT', export_yup=True, export_force_sampling=True,
        export_optimize_animation_size=True, export_def_bones=False)

# ---------- プレビュー（形の確認用） ----------
def preview(tag):
    bpy.ops.mesh.primitive_plane_add(size=20)
    g = bpy.context.object; g.data.materials.append(mat("Ground", srgb("#7fbf6a"), 0.9))
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN')); link(sun)
    sun.data.energy = 3.2; sun.rotation_euler = (0.9, 0.2, -0.6)
    w = bpy.data.worlds.new("w"); scene.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*srgb("#bfe3f7"), 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sc = scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 24; sc.cycles.device = 'CPU'
    sc.render.resolution_x = 640; sc.render.resolution_y = 480
    sc.view_settings.view_transform = 'Standard'
    target = bpy.data.objects.new("T", None); link(target); target.location = (0, -0.25, 1.05)
    for nm, loc in (("side", (5.0, -0.25, 1.3)), ("front", (2.8, -4.0, 1.8)), ("back", (-3.2, 3.4, 2.2))):
        cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); link(cam)
        cam.data.lens = 50; cam.location = loc
        c = cam.constraints.new('TRACK_TO'); c.target = target
        sc.camera = cam
        sc.render.filepath = os.path.join(OUT, "prev_%s_%s.png" % (tag, nm))
        bpy.ops.render.render(write_still=True)

def pose_frames(tag):
    bpy.ops.mesh.primitive_plane_add(size=20)
    g = bpy.context.object; g.data.materials.append(mat("Ground", srgb("#7fbf6a"), 0.9))
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN')); link(sun)
    sun.data.energy = 3.2; sun.rotation_euler = (0.9, 0.2, -0.6)
    w = bpy.data.worlds.new("w"); scene.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*srgb("#bfe3f7"), 1)
    sc = scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 12; sc.cycles.device = 'CPU'
    sc.render.resolution_x = 360; sc.render.resolution_y = 300; sc.view_settings.view_transform = 'Standard'
    target = bpy.data.objects.new("T", None); link(target); target.location = (0, -0.2, 1.0)
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); link(cam); cam.data.lens = 45; cam.location = (5.2, -0.2, 1.2)
    c = cam.constraints.new('TRACK_TO'); c.target = target; sc.camera = cam
    rig.animation_data.action = A_GALLOP
    for f in (0, 4, 8, 12, 16, 20):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(OUT, "pose_%s_%02d.png" % (tag, f))
        bpy.ops.render.render(write_still=True)

if "export" in ARGS:
    export(os.path.join(OUT, "oyatsuderby_horse.glb"))
if "poses" in ARGS:
    pose_frames(ARGS[ARGS.index("poses")+1])
if "preview" in ARGS:
    preview(ARGS[ARGS.index("preview")+1] if len(ARGS) > ARGS.index("preview")+1 else "v1")
print("BUILD_OK", len(PARTS))

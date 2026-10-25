"""
Lucknow Photorealistic Polygon & Infrastructure Map Generator
Creates river waterway, lush parks, urban sectors, building blocks, and ANPR cameras.
"""
import os
import math
from pathlib import Path

def offset_polyline(pts, offset):
    left_pts = []
    right_pts = []
    for i in range(len(pts)):
        p = pts[i]
        if i == 0:
            dx = pts[1][0] - p[0]
            dy = pts[1][1] - p[1]
        elif i == len(pts) - 1:
            dx = p[0] - pts[i-1][0]
            dy = p[1] - pts[i-1][1]
        else:
            dx = pts[i+1][0] - pts[i-1][0]
            dy = pts[i+1][1] - pts[i-1][1]
        length = math.hypot(dx, dy)
        if length == 0:
            nx, ny = 0, 1
        else:
            nx = -dy / length
            ny = dx / length
        left_pts.append((round(p[0] + nx * offset, 2), round(p[1] + ny * offset, 2)))
        right_pts.append((round(p[0] - nx * offset, 2), round(p[1] - ny * offset, 2)))
    return left_pts + right_pts[::-1]

def pts_str(pts):
    return ' '.join(f"{x:.2f},{y:.2f}" for x, y in pts)

centerline = [
    (3800, 12000), (4500, 11000), (5400, 10100), (6300, 9500),
    (7300, 9000), (8100, 8600), (8700, 8300), (8900, 7600),
    (8800, 6800), (8650, 5800), (9200, 4800), (10200, 4000),
    (11500, 3300), (13000, 2700), (14200, 2200)
]
river_poly = offset_polyline(centerline, 85.0)
riverfront_north = offset_polyline(centerline, 145.0)

parks = [
    ('janeshwar_mishra_park', 'leisure.park', '88,185,95,230', '-8', [
        (9200, 6900), (10600, 6700), (10800, 6100), (10400, 5700), (9300, 5900), (9100, 6400)
    ]),
    ('ambedkar_memorial_park', 'leisure.park', '78,168,88,230', '-8', [
        (8200, 7900), (8800, 7800), (8750, 7200), (8250, 7300)
    ]),
    ('lohia_park', 'leisure.park', '92,192,100,230', '-8', [
        (8900, 7950), (9450, 7900), (9400, 7450), (8950, 7500)
    ]),
    ('lucknow_zoo_narhi', 'leisure.park', '82,175,90,230', '-8', [
        (6200, 7700), (6800, 7650), (6750, 7150), (6250, 7200)
    ]),
    ('residency_historic_grounds', 'historic', '100,185,110,230', '-8', [
        (5400, 9300), (6000, 9250), (5950, 8750), (5450, 8800)
    ]),
    ('gomti_riverfront_greenway', 'landuse.park', '95,190,105,200', '-9', riverfront_north)
]

districts = [
    ('hazratganj_cbd', 'landuse.commercial', '220,224,230,160', '-7', [
        (5900, 7900), (7100, 7850), (7050, 6800), (5850, 6850)
    ]),
    ('gomti_nagar_extension', 'landuse.residential', '228,230,235,150', '-7', [
        (8800, 7100), (11200, 6900), (11000, 4800), (8600, 5100)
    ]),
    ('alambagh_transit_hub', 'landuse.commercial', '225,225,228,150', '-7', [
        (4500, 5500), (5800, 5450), (5750, 4200), (4450, 4250)
    ]),
    ('indira_nagar_sector', 'landuse.residential', '230,232,238,150', '-7', [
        (8200, 10200), (10500, 10100), (10400, 8600), (8100, 8700)
    ])
]

# Building clusters around the arterial junction cluster_11823984553
# Intersection is around (8500, 5700) - (8800, 6000)
buildings = []
bx, by = 8600, 6050
for row in range(5):
    for col in range(6):
        cx = bx + col * 45
        cy = by + row * 40
        b_pts = [(cx, cy), (cx + 32, cy), (cx + 32, cy + 28), (cx, cy + 28)]
        buildings.append((f'bldg_n_{row}_{col}', 'building', '210,215,225,240', '-3', b_pts))

# Buildings south of intersection
bx2, by2 = 8600, 5450
for row in range(4):
    for col in range(6):
        cx = bx2 + col * 45
        cy = by2 + row * 38
        b_pts = [(cx, cy), (cx + 34, cy), (cx + 34, cy + 26), (cx, cy + 26)]
        buildings.append((f'bldg_s_{row}_{col}', 'building', '215,220,228,240', '-3', b_pts))

# Police HQ building & campus
police_campus = [(7050, 7350), (7250, 7350), (7250, 7200), (7050, 7200)]
buildings.append(('police_hq_campus', 'amenity.police', '60,85,140,255', '-2', police_campus))

lines = ['<additional>']
# Water layer
lines.append(f'    <poly id="gomti_river_main" type="waterway" color="65,145,225,240" fill="1" layer="-10" shape="{pts_str(river_poly)}"/>')

# Parks
for pid, ptype, col, layer, pts in parks:
    lines.append(f'    <poly id="{pid}" type="{ptype}" color="{col}" fill="1" layer="{layer}" shape="{pts_str(pts)}"/>')

# Districts
for did, dtype, col, layer, pts in districts:
    lines.append(f'    <poly id="{did}" type="{dtype}" color="{col}" fill="1" layer="{layer}" shape="{pts_str(pts)}"/>')

# Buildings
for bid, btype, col, layer, pts in buildings:
    lines.append(f'    <poly id="{bid}" type="{btype}" color="{col}" fill="1" layer="{layer}" shape="{pts_str(pts)}"/>')

# POIs
pois = [
    ('POI_POLICE_ICCC_HQ', 'Police Command HQ', '30,80,210,255', '200', 7150.0, 7275.0, 14.0, 14.0),
    ('POI_ANPR_CAM_01', 'ANPR Camera #01 (Hazratganj)', '255,200,0,255', '180', 6800.0, 7200.0, 10.0, 10.0),
    ('POI_ANPR_CAM_02', 'ANPR Camera #02 (Gomti Barrage)', '255,200,0,255', '180', 8700.0, 8300.0, 10.0, 10.0),
    ('POI_ANPR_CAM_03', 'ANPR Camera #03 (Shaheed Path)', '255,200,0,255', '180', 8650.0, 5800.0, 10.0, 10.0),
]
for p_id, p_type, col, layer, x, y, w, h in pois:
    lines.append(f'    <poi id="{p_id}" type="{p_type}" color="{col}" layer="{layer}" x="{x}" y="{y}" width="{w}" height="{h}"/>')

lines.append('</additional>')

out_path = Path(__file__).resolve().parent / "lucknow.poly.xml"
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
print(f"Generated photorealistic polygons: {len(lines)} lines -> {out_path}")

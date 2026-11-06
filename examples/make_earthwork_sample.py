"""Create a small, fictional site in DXF units of metres."""
from pathlib import Path
import ezdxf

path = Path('output/earthwork-input/site.dxf')
path.parent.mkdir(parents=True, exist_ok=True)
doc = ezdxf.new()
m = doc.modelspace()
for y in (0, 5, 10):
    m.add_lwpolyline([(0, y), (10, y)], dxfattribs={'layer': 'CONTOURS', 'elevation': y / 5})
m.add_polyline3d([(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)], close=True, dxfattribs={'layer': 'PAD'})
doc.saveas(path)
print(path)

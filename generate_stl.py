import trimesh
import numpy as np

# Create a 10x10x10 unit cube (default is usually mm in 3D printing context, but trimesh is unitless)
# If we treat it as mm: 10mm x 10mm x 10mm = 1000 mm^3 = 1 cm^3
mesh = trimesh.creation.box(extents=[10, 10, 10]) 
mesh.export('test_cube.stl')
print("Created test_cube.stl")

"""Room air-domain operations, including imported solid-obstacle subtraction."""
import math
import numpy as np


def create_room_domain(length_x=6.0, length_y=4.0, height=3.0,
                       nx=24, ny=16, nz=12,
                       inlet_wall="x_min", outlet_wall="x_max",
                       opening_width_fraction=0.35,
                       opening_height_fraction=0.55,
                       max_cells=50000):
    """Create a cell-centred rectangular air domain and wall aperture masks."""
    dims = np.asarray([length_x, length_y, height], dtype=float)
    counts = np.asarray([nx, ny, nz], dtype=int)
    if not np.isfinite(dims).all() or np.any(dims <= 0):
        raise ValueError("Panjang, lebar, dan tinggi ruangan harus positif.")
    if np.any(counts < 4) or np.any(counts > 50):
        raise ValueError("Jumlah sel setiap sumbu harus antara 4 dan 50.")
    total = int(np.prod(counts))
    if total > int(max_cells):
        raise ValueError(f"Jumlah sel {total:,} melebihi batas {max_cells:,}. Kurangi resolusi.")
    valid_pairs = {"x_min":"x_max","x_max":"x_min","y_min":"y_max","y_max":"y_min","z_min":"z_max","z_max":"z_min"}
    if inlet_wall not in valid_pairs or valid_pairs[inlet_wall] != outlet_wall:
        raise ValueError("Inlet dan outlet harus berada pada dua sisi berlawanan.")
    for value in (opening_width_fraction, opening_height_fraction):
        if not np.isfinite(value) or value <= 0 or value > 1:
            raise ValueError("Ukuran bukaan harus antara 0 dan 1 dari dimensi dinding.")
    dx, dy, dz = dims / counts
    x = (np.arange(nx) + 0.5) * dx
    y = (np.arange(ny) + 0.5) * dy
    z = (np.arange(nz) + 0.5) * dz
    mask = np.ones((nz, ny, nx), dtype=bool)
    inlet = np.zeros_like(mask)
    outlet = np.zeros_like(mask)
    axis_name, side = inlet_wall[0], inlet_wall.endswith("min")
    if axis_name == "x":
        face_in=(slice(None),slice(None),0 if side else -1); face_out=(slice(None),slice(None),-1 if side else 0)
        y0=(1-opening_width_fraction)/2; z0=(1-opening_height_fraction)/2
        yi=(y>=y0*length_y)&(y<=(y0+opening_width_fraction)*length_y)
        zi=(z>=z0*height)&(z<=(z0+opening_height_fraction)*height)
        patch=zi[:,None]&yi[None,:]; inlet[face_in]=patch; outlet[face_out]=patch
    elif axis_name == "y":
        face_in=(slice(None),0 if side else -1,slice(None)); face_out=(slice(None),-1 if side else 0,slice(None))
        x0=(1-opening_width_fraction)/2; z0=(1-opening_height_fraction)/2
        xi=(x>=x0*length_x)&(x<=(x0+opening_width_fraction)*length_x)
        zi=(z>=z0*height)&(z<=(z0+opening_height_fraction)*height)
        patch=zi[:,None]&xi[None,:]; inlet[face_in]=patch; outlet[face_out]=patch
    else:
        face_in=(0 if side else -1,slice(None),slice(None)); face_out=(-1 if side else 0,slice(None),slice(None))
        x0=(1-opening_width_fraction)/2; y0=(1-opening_width_fraction)/2
        xi=(x>=x0*length_x)&(x<=(x0+opening_width_fraction)*length_x)
        yi=(y>=y0*length_y)&(y<=(y0+opening_width_fraction)*length_y)
        patch=yi[:,None]&xi[None,:]; inlet[face_in]=patch; outlet[face_out]=patch
    direction={"x_min":[1.,0.,0.],"x_max":[-1.,0.,0.],"y_min":[0.,1.,0.],"y_max":[0.,-1.,0.],"z_min":[0.,0.,1.],"z_max":[0.,0.,-1.]}[inlet_wall]
    zz,yy,xx=np.meshgrid(z,y,x,indexing="ij")
    centers=np.column_stack((xx.ravel(),yy.ravel(),zz.ravel()))
    return {
        "shape":"Rectangular room air domain","inside_mask_zyx":mask,
        "inlet_mask_zyx":inlet,"outlet_mask_zyx":outlet,"cell_centers":centers,
        "x":x,"y":y,"z":z,"nx":int(nx),"ny":int(ny),"nz":int(nz),
        "dx":float(dx),"dy":float(dy),"dz":float(dz),"active_cell_count":total,
        "candidate_cell_count":total,"volume_estimate_m3":float(np.prod(dims)),
        "bounds_min_m":[0.,0.,0.],"bounds_max_m":dims.tolist(),
        "inlet_wall":inlet_wall,"outlet_wall":outlet_wall,
        "inlet_cell_count":int(inlet.sum()),"outlet_cell_count":int(outlet.sum()),
        "velocity_direction":direction,"mesh_type":"rectangular room Cartesian air-domain",
        "boundary_note":"Inlet/outlet rectangular apertures; remaining room boundaries are impermeable in this MVP.",
    }


def subtract_solid_obstacle(room_domain, vertices, faces, scale=1.0,
                            translation=(0.0,0.0,0.0), max_faces=250000):
    """Remove cells inside a watertight imported solid from a room's air mask.

    Imported geometry is transformed by uniform scale and XYZ translation in
    metres. Point-in-solid uses vertical ray parity against a spatial XY binning
    of triangles. This is a voxel occupancy approximation, not CAD Boolean.
    """
    vertices=np.asarray(vertices,dtype=float); faces=np.asarray(faces,dtype=np.int64)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or len(vertices)<4 or faces.ndim!=2 or faces.shape[1]!=3 or len(faces)<4:
        raise ValueError("Geometri obstacle harus memiliki vertex dan segitiga 3D.")
    if len(faces)>int(max_faces) or not np.isfinite(vertices).all() or faces.min()<0 or faces.max()>=len(vertices):
        raise ValueError("Data obstacle tidak valid atau melebihi batas face.")
    scale=float(scale); shift=np.asarray(translation,dtype=float)
    if not np.isfinite(scale) or scale<=0 or scale>1000 or shift.shape!=(3,) or not np.isfinite(shift).all():
        raise ValueError("Skala dan translasi obstacle tidak valid.")
    edges=np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])); edges.sort(axis=1)
    _,counts=np.unique(edges,axis=0,return_counts=True)
    if np.any(counts!=2):
        raise ValueError("Obstacle harus berupa permukaan tertutup/manifold (watertight).")
    tri=(vertices*scale+shift)[faces]
    lower=tri.reshape(-1,3).min(axis=0); upper=tri.reshape(-1,3).max(axis=0)
    x=np.asarray(room_domain["x"]); y=np.asarray(room_domain["y"]); z=np.asarray(room_domain["z"])
    dx=float(room_domain["dx"]); dy=float(room_domain["dy"])
    nx,ny=len(x),len(y)
    bins=[[[] for _ in range(nx)] for _ in range(ny)]
    room_min=np.asarray(room_domain["bounds_min_m"],dtype=float)
    for fi,t in enumerate(tri):
        tmin=t[:,:2].min(axis=0); tmax=t[:,:2].max(axis=0)
        ix0=max(0,int(math.ceil((tmin[0]-room_min[0])/dx-0.5)))
        ix1=min(nx-1,int(math.floor((tmax[0]-room_min[0])/dx-0.5)))
        iy0=max(0,int(math.ceil((tmin[1]-room_min[1])/dy-0.5)))
        iy1=min(ny-1,int(math.floor((tmax[1]-room_min[1])/dy-0.5)))
        if ix0<=ix1 and iy0<=iy1:
            for iy in range(iy0,iy1+1):
                for ix in range(ix0,ix1+1): bins[iy][ix].append(fi)
    inside=np.zeros_like(room_domain["inside_mask_zyx"],dtype=bool)
    eps=max(dx,dy,float(room_domain["dz"]))*1e-9
    for iy,yc in enumerate(y):
        for ix,xc in enumerate(x):
            hits=[]
            for fi in bins[iy][ix]:
                t=tri[fi]; a,b,c=t
                v0=b[:2]-a[:2]; v1=c[:2]-a[:2]; v2=np.array([xc+dx*1.234567e-7,yc+dy*2.345679e-7])-a[:2]
                den=v0[0]*v1[1]-v1[0]*v0[1]
                if abs(den)<=1e-14: continue
                u=(v2[0]*v1[1]-v1[0]*v2[1])/den
                v=(v0[0]*v2[1]-v2[0]*v0[1])/den
                w=1-u-v
                if u>=-1e-10 and v>=-1e-10 and w>=-1e-10:
                    hits.append(float(w*a[2]+u*b[2]+v*c[2]))
            if hits:
                hits.sort(); unique=[]
                for h in hits:
                    if not unique or abs(h-unique[-1])>eps: unique.append(h)
                inside[:,iy,ix]=(np.searchsorted(np.asarray(unique),z,side="right")%2)==1
    original=room_domain["inside_mask_zyx"]
    removed=original & inside
    remaining=original & ~inside
    if not np.any(removed):
        raise ValueError("Obstacle tidak mengenai sel domain ruangan. Periksa posisi, skala, dan satuan model.")
    if not np.any(remaining):
        raise ValueError("Obstacle memenuhi seluruh ruangan; tidak tersisa domain udara.")
    result=dict(room_domain)
    result["inside_mask_zyx"]=remaining
    result["inlet_mask_zyx"]=room_domain["inlet_mask_zyx"] & remaining
    result["outlet_mask_zyx"]=room_domain["outlet_mask_zyx"] & remaining
    zz,yy,xx=np.meshgrid(z,y,x,indexing="ij")
    result["cell_centers"]=np.column_stack((xx[remaining],yy[remaining],zz[remaining]))
    result["active_cell_count"]=int(remaining.sum())
    result["solid_cell_count"]=int(removed.sum())
    result["volume_estimate_m3"]=float(remaining.sum()*room_domain["dx"]*room_domain["dy"]*room_domain["dz"])
    result["inlet_cell_count"]=int(result["inlet_mask_zyx"].sum())
    result["outlet_cell_count"]=int(result["outlet_mask_zyx"].sum())
    result["shape"]="Room air domain with imported solid obstacle"
    result["obstacle_bounds_min_m"]=(lower).tolist()
    result["obstacle_bounds_max_m"]=(upper).tolist()
    result["mesh_type"]="voxel room air domain with subtracted imported solid"
    result["boundary_note"]="Imported watertight solid removed from room air cells by voxel occupancy; no-slip and thermal wall coupling are not solved."
    return result

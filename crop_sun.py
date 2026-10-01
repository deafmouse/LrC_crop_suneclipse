import os
import io
import re
import math
import rawpy
import cv2
import numpy as np
from PIL import Image

# ----------------- CONFIGURATION -----------------
CROP_EDGE_PX = 2000

RAW_DIRS = [
    "/Photo_1",
    "/Photo_2",
    "/Photo_3"
]
# -------------------------------------------------

def get_preview_from_cr3(cr3_path):
    try:
        with rawpy.imread(cr3_path) as raw:
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    im = Image.open(io.BytesIO(thumb.data))
                    im.load()
                    return im
            except Exception:
                pass
            rgb = raw.postprocess(half_size=True, use_camera_wb=False)
            return Image.fromarray(rgb)
    except Exception as e:
        print(f"    [!] Error reading {os.path.basename(cr3_path)}: {e}")
        return None

def circle_from_3_pts(p1, p2, p3):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-6:
        return None, None, None
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = np.sqrt((x1 - ux)**2 + (y1 - uy)**2)
    return ux, uy, r

def find_reference_radius(image_paths):
    print("[*] PASS 1: Scanning for solar radius calibration...")
    for path in image_paths:
        im = get_preview_from_cr3(path)
        if im is None:
            continue
        gray = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
        max_val = float(np.max(gray))
        if max_val < 180:
            continue
        _, thresh = cv2.threshold(gray, int(max_val * 0.85), 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            perimeter = cv2.arcLength(c, True)
            if area > 1000 and perimeter > 0:
                circularity = 4 * np.pi * (area / (perimeter * perimeter))
                if circularity > 0.85:
                    (_, _), radius = cv2.minEnclosingCircle(c)
                    print(f"    [+] Calibrated against: {os.path.basename(path)} (Radius: {radius:.1f}px)")
                    return radius
    print("    [!] Defaulting solar radius estimate to 175.0px.")
    return 175.0

def detect_sun_hybrid(im, target_r):
    gray = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    max_val = float(np.max(blurred))

    if max_val < 20:
        return None, None

    if max_val < 220:
        edges = cv2.Canny(blurred, 15, 60)
    else:
        edges = cv2.Canny(blurred, int(max_val * 0.35), int(max_val * 0.75))

    y_pts, x_pts = np.where(edges > 0)
    
    if len(x_pts) >= 40:
        edge_points = np.column_stack([x_pts, y_pts])
        num_pts = len(edge_points)
        best_inliers = 0
        best_center = None

        for _ in range(1000):
            idx = np.random.choice(num_pts, 3, replace=False)
            xc, yc, r = circle_from_3_pts(edge_points[idx[0]], edge_points[idx[1]], edge_points[idx[2]])
            if xc is None or abs(r - target_r) > (target_r * 0.10):
                continue
            dists = np.sqrt((edge_points[:, 0] - xc)**2 + (edge_points[:, 1] - yc)**2)
            inliers = np.sum(np.abs(dists - target_r) < 3.0)
            if inliers > best_inliers:
                best_inliers = inliers
                best_center = (xc, yc)

        if best_center is not None and best_inliers >= 15:
            cx, cy = float(best_center[0]), float(best_center[1])
            if not (math.isnan(cx) or math.isnan(cy)):
                return cx, cy

    thresh_val = max(35, int(max_val * 0.85))
    binary_mask = (gray >= thresh_val).astype(np.uint8)
    y_idx, x_idx = np.where(binary_mask > 0)

    if len(x_idx) > 0:
        cx = float(np.mean(x_idx))
        cy = float(np.mean(y_idx))
        if not (math.isnan(cx) or math.isnan(cy)):
            return cx, cy

    return None, None

def write_safe_crop_to_xmp(xmp_path, top, left, bottom, right):
    if any(math.isnan(v) for v in [top, left, bottom, right]):
        return False

    top = max(0.000001, min(0.999999, top))
    left = max(0.000001, min(0.999999, left))
    bottom = max(0.000001, min(0.999999, bottom))
    right = max(0.000001, min(0.999999, right))

    try:
        with open(xmp_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        crop_attrs = [
            "crs:HasCrop", "crs:CropTop", "crs:CropLeft", 
            "crs:CropBottom", "crs:CropRight", "crs:CropAngle", 
            "crs:CropConstrainToWarp", "crs:CropUnit"
        ]
        for attr in crop_attrs:
            content = re.sub(rf"\s+{attr}=\"[^\"]*\"", "", content)
            content = re.sub(rf"\s*<{attr}>.*?\s*", "", content)

        crop_block = (
            f" crs:HasCrop=\"True\""
            f" crs:CropTop=\"{top:.6f}\""
            f" crs:CropLeft=\"{left:.6f}\""
            f" crs:CropBottom=\"{bottom:.6f}\""
            f" crs:CropRight=\"{right:.6f}\""
            f" crs:CropAngle=\"0\""
            f" crs:CropConstrainToWarp=\"0\""
            f" crs:CropUnit=\"0\""
        )
        
        target_tag = "<rdf:Description"
        if target_tag in content:
            content = content.replace(target_tag, target_tag + crop_block, 1)
        else:
            return False

        with open(xmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        return True

    except Exception as err:
        print(f"Write error on {os.path.basename(xmp_path)}: {err}")
        return False

# Main Processing Loop
matched_all = []
for folder in RAW_DIRS:
    if not os.path.exists(folder):
        continue
    for f in os.listdir(folder):
        if f.lower().endswith(".cr3"):
            cr3 = os.path.join(folder, f)
            base = os.path.splitext(cr3)[0]
            if os.path.exists(base + ".xmp"):
                matched_all.append((cr3, base + ".xmp"))
            elif os.path.exists(base + ".XMP"):
                matched_all.append((cr3, base + ".XMP"))

matched_all.sort(key=lambda x: x[0])
print(f"Found {len(matched_all)} file(s) across all directories.")
if len(matched_all) == 0:
    exit(0)

cr3_paths = [pair[0] for pair in matched_all]
calibrated_radius = find_reference_radius(cr3_paths)

print("PASS 2: Centering all frames safely...")
updated_count = 0

for idx, (cr3_path, xmp_path) in enumerate(matched_all, start=1):
    cr3_name = os.path.basename(cr3_path)
    im = get_preview_from_cr3(cr3_path)
    if im is None:
        continue

    pw, ph = im.size
    cx, cy = detect_sun_hybrid(im, calibrated_radius)

    if (cx is None) or (cy is None):
        print(f"{cr3_name}: Sun not detectable.")
        continue

    norm_cx = cx / pw
    norm_cy = cy / ph

    norm_box_w = CROP_EDGE_PX / 6000.0
    norm_box_h = CROP_EDGE_PX / 4000.0

    left = norm_cx - (norm_box_w / 2.0)
    right = norm_cx + (norm_box_w / 2.0)
    top = norm_cy - (norm_box_h / 2.0)
    bottom = norm_cy + (norm_box_h / 2.0)

    if left < 0.0:
        right += abs(left)
        left = 0.0
    if right > 1.0:
        left -= (right - 1.0)
        right = 1.0
    if top < 0.0:
        bottom += abs(top)
        top = 0.0
    if bottom > 1.0:
        top -= (bottom - 1.0)
        bottom = 1.0

    if write_safe_crop_to_xmp(xmp_path, top, left, bottom, right):
        print(f"[{idx}/{len(matched_all)}] {cr3_name} -> Center: ({norm_cx:.4f}, {norm_cy:.4f}) [✓]")
        updated_count += 1

print("\n" + "=" * 60)
print(f"Finished! Successfully applied centered crops to {updated_count}/{len(matched_all)} files.")
print("In Lightroom Classic, select all photos and click:")
print("Metadata -> Read Metadata from Files")

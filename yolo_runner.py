import os
import cv2
import numpy as np
import json
import argparse
from ultralytics import YOLO

def is_image_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp']

def is_video_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']

def draw_zones_on_frame(frame, zones):
    # zones: list of dicts with either {'type':'rect','coords':(x1,y1,x2,y2)}
    # or {'type':'poly','pts':np.array([[x,y],...])}
    for z in zones:
        try:
            if z.get('type') == 'poly' and 'pts' in z:
                pts = z['pts']
                if isinstance(pts, np.ndarray):
                    cv2.polylines(frame, [pts.astype(np.int32)], True, (0, 255, 255), 2)
            elif z.get('type') == 'rect' and 'coords' in z:
                x1, y1, x2, y2 = z['coords']
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 0), 2)
        except Exception:
            continue

def process_frame_counts(frame, model, zones):
    # zones: list of dicts as used in draw_zones_on_frame
    results = model(frame, stream=True, conf=0.25)
    # zone_counts: list of dicts mapping class->count
    zone_counts = [dict() for _ in range(len(zones))]
    class_counts = {}
    draw_zones_on_frame(frame, zones)
    det_index = 0
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            cls_name = model.names[cls_id]
            class_counts[cls_name] = class_counts.get(cls_name, 0) + 1
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            # draw
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)
            label = f"{cls_name} {class_counts[cls_name]}"
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            # assign to zones: support rects and polygons
            for i, z in enumerate(zones):
                try:
                    if z.get('type') == 'rect' and 'coords' in z:
                        zx1, zy1, zx2, zy2 = map(int, z['coords'])
                        if min(zx1, zx2) < cx < max(zx1, zx2) and min(zy1, zy2) < cy < max(zy1, zy2):
                            zone_counts[i][cls_name] = zone_counts[i].get(cls_name, 0) + 1
                    elif z.get('type') == 'poly' and 'pts' in z:
                        pts = z['pts']
                        # pointPolygonTest expects numpy array of shape Nx1x2 or Nx2
                        if isinstance(pts, np.ndarray):
                            # ensure correct shape
                            val = cv2.pointPolygonTest(pts.astype(np.int32), (float(cx), float(cy)), False)
                            if val >= 0:
                                zone_counts[i][cls_name] = zone_counts[i].get(cls_name, 0) + 1
                except Exception:
                    continue
            det_index += 1

    # annotate zone totals (per class)
    for i, z in enumerate(zones):
        x1, y1, x2, y2 = z
        # compose small text lines for each class
        y_off = 20
        for cls, cnt in zone_counts[i].items():
            cv2.putText(frame, f"{cls}: {cnt}", (x1 + 4, y1 + y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            y_off += 20

    total = sum(class_counts.values())
    return frame, zone_counts, class_counts, total

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', required=False, default=None, help='Path to input image or video')
    parser.add_argument('--output_dir', '-o', default='outputs', help='Directory to save outputs')
    parser.add_argument('--model', '-m', default='yolov8l.pt', help='Path to YOLO model weights (default: yolov8l.pt)')
    parser.add_argument('--zones', '-z', help='Path to zones JSON file (with name,x,y,w,h entries)')
    args = parser.parse_args()

    # If no input provided, print help and an example instead of raising an error
    if not args.input:
        parser.print_help()
        print('\nExample:')
        print('  python yolo_runner.py --input path/to/image.jpg --output_dir outputs --zones path/to/zones.json')
        return

    input_path = args.input
    output_dir = args.output_dir
    zones_file_arg = args.zones
    os.makedirs(output_dir, exist_ok=True)

    # Load model specified by user or default to yolov8l
    model_path = args.model
    if not os.path.isabs(model_path):
        # try relative to script dir first
        candidate = os.path.join(os.getcwd(), model_path)
    else:
        candidate = model_path

    if not os.path.exists(candidate):
        print(json.dumps({'success': False, 'message': f"Model file not found: {candidate}. Please place '{model_path}' in the working directory or pass --model with an absolute path."}))
        return

    model = YOLO(candidate)

    # Load zones: from provided zones file or fallback to zones.json in cwd
    zones = []
    if zones_file_arg and os.path.exists(zones_file_arg):
        try:
            zones = json.load(open(zones_file_arg))
        except Exception:
            zones = []
    else:
        zones_file = os.path.join(os.getcwd(), 'zones.json')
        if os.path.exists(zones_file):
            try:
                zones = json.load(open(zones_file))
            except Exception:
                zones = []

    # Normalize zone format to list of dicts supporting rectangles and polygons
    # Each entry will be either {'type':'rect','coords':(x1,y1,x2,y2),'name':..., 'selected':bool}
    # or {'type':'poly','pts':np.array([[x,y],...]), 'name':..., 'selected':bool}
    normalized_zones = []
    for z in zones:
        if isinstance(z, dict):
            name = z.get('name', '')
            sel = z.get('selected', True)
            # polygon style: 'points' or 'pts' (list of [x,y])
            pts = None
            if 'points' in z and isinstance(z['points'], (list, tuple)) and len(z['points']) > 2:
                pts = np.array(z['points'], dtype=np.int32)
            elif 'pts' in z and isinstance(z['pts'], (list, tuple)) and len(z['pts']) > 2:
                pts = np.array(z['pts'], dtype=np.int32)

            if pts is not None:
                normalized_zones.append({'type': 'poly', 'pts': pts, 'name': name, 'selected': bool(sel)})
            else:
                # fallback to rectangle format x,y,w,h
                x = int(z.get('x', 0))
                y = int(z.get('y', 0))
                w = int(z.get('w', 0))
                h = int(z.get('h', 0))
                normalized_zones.append({'type': 'rect', 'coords': (x, y, x + w, y + h), 'name': name, 'selected': bool(sel)})
        elif isinstance(z, (list, tuple)) and len(z) >= 4:
            # list of rectangle coords
            x1, y1, x2, y2 = map(int, (z[0], z[1], z[2], z[3]))
            normalized_zones.append({'type': 'rect', 'coords': (x1, y1, x2, y2), 'name': '', 'selected': True})
        elif isinstance(z, (list, tuple)) and len(z) > 2:
            # list of points (poly)
            try:
                pts = np.array(z, dtype=np.int32)
                if pts.shape[0] > 2 and pts.shape[1] >= 2:
                    normalized_zones.append({'type': 'poly', 'pts': pts, 'name': '', 'selected': True})
            except Exception:
                continue

    # If image
    selected_zones = [zz for zz in normalized_zones if zz.get('selected', True)]

    if is_image_file(input_path):
        frame = cv2.imread(input_path)
        if frame is None:
            print(json.dumps({'success': False, 'message': f'Could not read image: {input_path}'}))
            return
        out_frame, zone_counts, class_counts, total = process_frame_counts(frame, model, selected_zones)
        base = os.path.splitext(os.path.basename(input_path))[0]
        out_path = os.path.abspath(os.path.join(output_dir, f'annotated_{base}.jpg'))
        # Draw zone names and counts on final frame (overlay with names and aggregated counts)
        for idx, z in enumerate(selected_zones):
            name = z.get('name', f'Zone {idx+1}')
            counts = zone_counts[idx] if idx < len(zone_counts) else {}
            total_in_zone = sum(counts.values())
            # choose text position
            if z.get('type') == 'rect':
                x1, y1, x2, y2 = z['coords']
                tx, ty = int(x1) + 4, int(y1) + 16
            else:
                pts = z.get('pts')
                if isinstance(pts, np.ndarray):
                    bx, by, bw, bh = cv2.boundingRect(pts)
                    tx, ty = bx + 4, by + 16
                else:
                    tx, ty = 4, 16
            cv2.putText(out_frame, f"{name}: {total_in_zone}", (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,0), 2)
        cv2.imwrite(out_path, out_frame)
        # prepare zones metadata with per-class counts
        zones_meta = []
        for idx, z in enumerate(selected_zones):
            zones_meta.append({'name': z.get('name','Zone ' + str(idx+1)), 'counts': zone_counts[idx] if idx < len(zone_counts) else {}})
        result = {'success': True, 'annotated_path': out_path, 'zones': zones_meta, 'class_counts': class_counts, 'total': total}
        print(json.dumps(result))
        return

    # If video
    if is_video_file(input_path):
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            print(json.dumps({'success': False, 'message': f'Could not open video: {input_path}'}))
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        base = os.path.splitext(os.path.basename(input_path))[0]
        out_path = os.path.abspath(os.path.join(output_dir, f'annotated_{base}.mp4'))
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

        selected_zones = [zz for zz in normalized_zones if zz.get('selected', True)]
        cumulative_zone_counts = [ {} for _ in selected_zones ]
        cumulative_total = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            out_frame, zone_counts_frame, class_counts_frame, total_frame = process_frame_counts(frame, model, selected_zones)
            # accumulate counts
            cumulative_total += total_frame
            # ensure cumulative_zone_counts has dicts
            for i in range(len(selected_zones)):
                frame_zone_counts = zone_counts_frame[i] if i < len(zone_counts_frame) else {}
                for cls, cnt in frame_zone_counts.items():
                    cumulative_zone_counts[i][cls] = cumulative_zone_counts[i].get(cls, 0) + cnt
            # accumulate class totals
            for cls, cnt in class_counts_frame.items():
                cumulative_total = cumulative_total  # cumulative_total already adds total_frame
                cumulative_total  # noop to satisfy linter
            # accumulate overall class counts
            # use a proper dict to accumulate
            if 'overall_class_counts' not in locals():
                overall_class_counts = {}
            for cls, cnt in class_counts_frame.items():
                overall_class_counts[cls] = overall_class_counts.get(cls, 0) + cnt
            writer.write(out_frame)

        cap.release()
        writer.release()
        # build zones metadata
        zones_meta = []
        for idx, z in enumerate(selected_zones):
            zones_meta.append({'name': z.get('name','Zone ' + str(idx+1)), 'counts': cumulative_zone_counts[idx] if idx < len(cumulative_zone_counts) else {}})
        result = {'success': True, 'annotated_path': out_path, 'zones': zones_meta, 'class_counts': overall_class_counts if 'overall_class_counts' in locals() else {}, 'total': cumulative_total}
        print(json.dumps(result))
        return

    print(json.dumps({'success': False, 'message': 'Unsupported input type'}))

if __name__ == '__main__':
    main()

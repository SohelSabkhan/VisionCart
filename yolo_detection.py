import cv2
import numpy as np
from pathlib import Path
import torch

class YOLODetector:
    def __init__(self, model_path='static/models/yolo11m_model.pt'):
        self.model_path = model_path
        self.model = None
        self.is_initialized = False

    def initialize(self):
        try:
            from ultralytics import YOLO

            if not Path(self.model_path).exists():
                print(f"Warning: YOLO model not found at {self.model_path}")
                print("Please place your trained best.pt model in static/models/")
                return False

            # Fix for PyTorch 2.6 - allow loading custom YOLO weights
            try:
                # Method 1: Add safe globals (recommended if available)
                torch.serialization.add_safe_globals([
                    'ultralytics.nn.tasks.DetectionModel',
                    'ultralytics.nn.modules.block.C2f',
                    'ultralytics.nn.modules.conv.Conv',
                    'ultralytics.nn.modules.head.Detect'
                ])
                self.model = YOLO(self.model_path)
            except AttributeError:
                # Method 2: Load with weights_only=False (fallback for older PyTorch)
                import warnings
                warnings.filterwarnings('ignore', category=FutureWarning)
                
                # Temporarily set torch to allow unsafe loading
                original_weights_only = torch.serialization.DEFAULT_PROTOCOL
                try:
                    # Load model with weights_only=False
                    self.model = YOLO(self.model_path)
                except Exception as e:
                    # If still fails, try monkey-patching torch.load
                    original_load = torch.load
                    torch.load = lambda *args, **kwargs: original_load(*args, **{**kwargs, 'weights_only': False})
                    try:
                        self.model = YOLO(self.model_path)
                    finally:
                        torch.load = original_load

            self.is_initialized = True
            print(f"✓ YOLO model loaded successfully from {self.model_path}")
            
            # Print available classes
            if hasattr(self.model, 'names'):
                print(f"✓ Model can detect {len(self.model.names)} classes:")
                for idx, name in self.model.names.items():
                    print(f"  - {name}")
            
            return True

        except ImportError:
            print("Warning: ultralytics package not installed")
            print("Install it with: pip install ultralytics")
            return False
        except Exception as e:
            print(f"Error initializing YOLO model: {e}")
            return False

    def detect(self, image):
        if not self.is_initialized:
            return []

        try:
            results = self.model(image, conf=0.5, verbose=False)

            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    class_name = result.names[cls_id]

                    detections.append({
                        'class': class_name,
                        'confidence': confidence
                    })

            return detections

        except Exception as e:
            print(f"Error during detection: {e}")
            return []

    def detect_from_frame(self, frame_data):
        if not self.is_initialized:
            return []

        try:
            nparr = np.frombuffer(frame_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                return []

            return self.detect(img)

        except Exception as e:
            print(f"Error processing frame: {e}")
            return []
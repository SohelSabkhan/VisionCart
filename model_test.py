from ultralytics import YOLO
model = YOLO('static/models/yolo11m_model.pt')
print(model.names)  # This shows all class names your model can detect
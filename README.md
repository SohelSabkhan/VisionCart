# VisionCart 🛒

**Smart Billing System using YOLO Object Detection + Flask**

VisionCart is an intelligent billing and item-recognition system designed for supermarkets, grocery stores, and retail shops.
Using **YOLO object detection**, the system identifies grocery items through a camera feed, counts them, and automatically generates a **bill with total price**, removing manual barcode scanning.

---

## 🚀 Features

### 🔍 **1. Real-time Object Detection (YOLO11 Model)**

* Detects grocery items using a trained YOLO model (`yolo11m_model.pt`).
* Counts the items accurately.
* Tracks multiple items simultaneously.

### 📄 **2. Smart Billing**

* Automatically generates a bill based on identified items.
* Prices are fetched from `items.json`.
* Final total amount is displayed.

### 🧾 **3. Billing Page with Payment Options**

Includes:

* Cart summary
* Payment page
* Mobile payment options (UPI, etc.)

### 🧑‍💻 **4. User Authentication**

* Login
* Signup
* Session management

### 🖥️ **5. Clean UI (Bootstrap + Custom CSS)**

* Light/Dark Mode
* Responsive design
* Modern shopping-cart theme

---

## 🗂️ Project Structure

```
VisionCart/
│
├── app.py                     # Main Flask app
├── models.py                  # Database models (if used)
├── yolo_detection.py          # YOLO inference logic
├── generate_complete_items.py # Dataset utilities
│
├── static/
│   ├── css/
│   ├── images/
│   ├── js/
│   └── models/                # YOLO model file (yolo11m_model.pt)
│
├── templates/
│   ├── home.html
│   ├── history.html
│   ├── login.html
│   ├── signup.html
│   ├── payment.html
│   ├── mobile_payment.html
│   └── home_1.html
│
└── requirements.txt
```

---

## 🛠️ Tech Stack

### **Backend**

* Python
* Flask
* YOLO11 (Ultralytics)
* OpenCV

### **Frontend**

* HTML
* CSS
* Bootstrap
* JavaScript

### **Database**

* JSON file (for item prices)
* Future-ready for PostgreSQL or MySQL

---

## ⚙️ How to Run Locally

### 1. Clone the repository

```
git clone https://github.com/SohelSabkhan/VisionCart.git
cd VisionCart
```

### 2. Install dependencies

```
pip install -r requirements.txt
```

### 3. Run the Flask App

```
python app.py
```

### 4. Open your browser

```
http://127.0.0.1:5000
```

---

## 📸 Screenshots


---

## 📦 Future Enhancements

* Add database support (PostgreSQL/MySQL)
* Add admin panel for item management
* Train model on more grocery items
* Add barcode + YOLO hybrid scanning
* Deploy on cloud (Render / AWS / Railway)

---

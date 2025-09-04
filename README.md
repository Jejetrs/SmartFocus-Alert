# Smart Focus Alert 👁️

**Real-time Focus Monitoring Application for Online Learning**

Smart Focus Alert is a web application that uses Computer Vision and MediaPipe technology to monitor user focus levels during online learning sessions in real-time. The system detects various distraction conditions such as drowsiness, yawning, loss of focus, and absence of users, then provides automatic alerts through visual text and audio notifications.

## 🎯 Key Features

### 📹 Live Monitoring
- **Real-time Detection**: Direct focus monitoring using camera
- **Multi-parameter Detection**: 
  - EAR (Eye Aspect Ratio) for drowsiness detection
  - MAR (Mouth Aspect Ratio) for yawning detection  
  - Iris position tracking for gaze direction detection
  - Face presence detection
- **Smart Alert System**: Audio alerts (Text-to-Speech + Beep) and visual notifications
- **Session Recording**: Record monitoring sessions with detection overlay
- **PDF Report**: Downloadable focus statistics report

### 📁 Upload Analysis  
- **File Support**: Image analysis (JPG, PNG, BMP) and video (MP4, AVI, MOV, MKV)
- **Multi-person Detection**: Detect multiple people in a single frame
- **Face Extraction**: Crop individual faces for separate analysis
- **Detailed Reports**: PDF reports with comprehensive detection statistics

## 🛠️ Technology Stack

### Backend
- **Python 3.11**
- **Flask 2.3.2** - Web framework
- **MediaPipe 0.10.5** - Computer vision and face detection
- **OpenCV 4.7.0.72** - Image processing
- **ReportLab 4.0.4** - PDF generation
- **Gunicorn** - Production WSGI server

### Frontend  
- **HTML5** - Page structure
- **CSS3** - Styling with glassmorphism design
- **JavaScript ES6+** - Interactive logic
- **Web APIs**: Camera, Speech Synthesis, Web Audio

### Cloud & Deployment
- **Railway** - Hosting platform
- **Docker** - Containerization
- **GitHub** - Version control and CI/CD

## 📋 System Requirements

### Minimum Requirements
- **OS**: Windows, macOS, Ubuntu (latest versions)
- **Browser**: Chrome, Firefox, Safari (modern versions)
- **RAM**: 4 GB minimum
- **Camera**: 720p resolution, 30 FPS
- **Internet**: Stable connection for application access

### Recommended
- **RAM**: 8 GB or more
- **Camera**: 1080p resolution
- **Lighting**: Adequate lighting for optimal face detection

## 🚀 Demo & Deployment
<img width="1895" height="824" alt="AppPreview" src="https://github.com/user-attachments/assets/9cb1df8d-4fdc-4730-9ea1-7707266ceb84" />

**Live Application**: [https://smartfocus.up.railway.app](https://smartfocus.up.railway.app)

**Repository**: [https://github.com/Jejetrs/SmartFocus-Alert.git](https://github.com/Jejetrs/SmartFocus-Alert.git)

## ⚡ Quick Start

### 1. Setup Virtual Environment
```bash
python -m venv env
source env/bin/activate  # Linux/Mac
# or
env\Scripts\activate  # Windows
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Application
```bash
python app.py
```

Application will run at `http://localhost:5000`

## 📊 Detection Parameters

### Threshold Values
| Parameter | Normal Range | Alert Threshold | Alert Duration |
|-----------|-------------|----------------|--------------|
| **EAR** (Eyes) | 0.2 - 0.4 | < 0.15 (Sleeping) | 8 seconds |
| **MAR** (Mouth) | 0.1 - 0.3 | > 0.5 (Yawning) | 3.5 seconds |
| **Iris Position** | Center ±2.5px | > 2.5px (Not Focused) | 8 seconds |
| **No Person** | Face detected | No face | 10 seconds |

### Audio Alerts
- **800 Hz**: Sleeping detection
- **600 Hz**: Yawning detection  
- **500 Hz**: No person detected
- **400 Hz**: Not focused detection

## 🎨 User Interface

### Navigation
- **Single Page Application (SPA)** with responsive navigation
- **Glassmorphism Design** for modern appearance
- **Mobile-friendly** with responsive layout

### Features per Page
- **Home**: Feature overview and system specifications
- **Live Monitoring**: Real-time detection with dashboard
- **Upload**: Drag & drop file analysis
- **Result**: Detection result visualization with comparison view

## 📁 Project Structure

```
SmartFocus-Alert/
├── app.py                 # Main backend using Flask, handles routing and server logic
├── static/                # Folder for static assets like JS, CSS, images
│   ├── js/
│   │   ├── index.js       # Homepage interactivity scripts
│   │   ├── live.js        # Live focus monitoring scripts
│   │   ├── upload.js      # File upload feature scripts
│   │   └── result.js      # Scripts to display detection/focus results
│   └── style/
│       ├── index.css      # Styling for homepage
│       ├── live.css       # Styling for live monitoring page
│       ├── upload.css     # Styling for file upload page
│       └── result.css     # Styling for results page
├── templates/             # HTML templates used by Flask
│   ├── index.html         # Homepage template
│   ├── live.html          # Live monitoring page template
│   ├── upload.html        # File upload page template
│   └── result.html        # Results page template
├── requirements.txt       # Python dependencies (Flask, OpenCV, etc.)
├── Dockerfile             # Docker configuration for containerizing the app
├── nixpacks.toml          # Deployment metadata & service configuration for Railway
├── Procfile               # Start command for Railway/Heroku deployment
├── railway.json           # Railway project configuration (project metadata)
├── railway.toml           # Railway config for environment, services, and build
└── README.md              # Project documentation (setup, usage, etc.)
```

## 🔧 API Endpoints

### Core Endpoints
- `GET /` - Homepage
- `GET /live` - Live monitoring interface  
- `GET/POST /upload` - File upload & analysis
- `GET /result` - Display analysis results

### API Routes
- `POST /process_frame` - Real-time frame processing
- `GET /get_monitoring_data` - Session statistics
- `POST /start_session` - Initialize monitoring session
- `POST /end_session` - Terminate session & generate reports
- `GET /health` - System health check

### File Serving
- `GET /download/<filename>` - Download PDF reports
- `GET /download_recording/<filename>` - Download session recordings

## 📈 Performance Metrics

### Accuracy Ratings
- **Excellent**: ≥ 90% focus accuracy
- **Good**: ≥ 75% focus accuracy  
- **Fair**: ≥ 60% focus accuracy
- **Poor**: ≥ 40% focus accuracy
- **Very Poor**: < 40% focus accuracy

### System Performance
- **Frame Processing**: Real-time (30 FPS)
- **Response Time**: < 100ms for detection
- **Memory Usage**: Optimized with circular buffer
- **Storage**: Temporary storage for privacy

## 🔒 Privacy & Security

- **Local Processing**: All analysis performed locally
- **Temporary Storage**: Data not permanently stored
- **No Cloud Upload**: Videos/images not sent to external servers
- **Secure Filename**: File name validation for security
- **Session-based**: Data deleted after session ends

## 🧪 Testing Results

### Black Box Testing
Functional testing on all components:
- ✅ Navigation system
- ✅ Live monitoring environment
- ✅ Detection model accuracy
- ✅ Alert notifications
- ✅ File generation
- ✅ Upload functionality
- ✅ Result visualization

### Usability Testing
- **Method**: SUS (System Usability Scale)
- **Participants**: 15 respondents (students, university students, supervisors)
- **Score**: 87.67/100 (Grade A+)
- **Result**: Excellent usability rating. Results show the system is **easy to understand, responsive, and beneficial** as online learning support.

## ⚠️ Troubleshooting

### Camera Issues

**Camera not detected / cannot access camera**
```
Solutions:
1. Ensure browser has camera access permission
2. Close other applications using the camera
3. Refresh page and allow camera access again
4. Check browser privacy settings (Chrome: Settings > Privacy > Site Settings > Camera)
5. Use HTTPS connection (live app: https://smartfocus.up.railway.app)
```

**Poor detection quality / inaccurate**
```
Solutions:
1. Ensure adequate lighting on face
2. Position face perpendicular to camera
3. Avoid backlight or lighting from behind
4. Clean camera lens
5. Use minimum 720p camera resolution
```

### Audio Issues

**Text-to-Speech not working**
```
Solutions:
1. Check system and browser volume settings
2. Ensure browser supports Web Speech API (Chrome, Firefox, Edge)
3. Check audio status in health indicator (audio icon in live monitoring)
4. Refresh page and reactivate audio toggle
5. Try different browser if problem persists
```

**Audio alert not audible**
```
Solutions:
1. Activate audio toggle on Live Monitoring page
2. Set volume to Medium or High level
3. Check operating system audio mixer
4. Ensure browser is not muted
5. Test with headphones if using external speakers
```

### File Upload Issues

**File cannot be uploaded**
```
Solutions:
1. Ensure file format is supported:
   - Images: JPG, JPEG, PNG, BMP
   - Videos: MP4, AVI, MOV, MKV
2. Check file size (maximum 100MB)
3. Try compressing file if too large
4. Check internet connection
5. Refresh page and try again
```

**Analysis process failed**
```
Solutions:
1. Ensure file is not corrupted
2. Try file with lower resolution
3. Check if file contains clear faces
4. Use more common file formats (MP4 for video, JPG for images)
```

### Browser Issues

**Application not loading correctly**
```
Solutions:
1. Clear browser cache and cookies
2. Disable browser extensions temporarily
3. Try incognito/private mode
4. Update browser to latest version
5. Try alternative browser (Chrome recommended)
```

**Layout displays incorrectly**
```
Solutions:
1. Refresh page
2. Check browser zoom level (100% recommended)
3. Disable dark mode extensions
4. Clear CSS cache
5. Use desktop browser (mobile not fully supported)
```

### Download Issues

**PDF/Video files cannot be downloaded**
```
Solutions:
1. Ensure popup blocker is not preventing download
2. Check browser download settings
3. Ensure sufficient storage space
4. Wait until file generation process completes
```

**File corrupted/cannot open**
```
Solutions:
1. Re-download file from application
2. Ensure download completed 100%
3. Try different PDF reader/video player
4. Check antivirus that might be blocking
```

### Error Messages

**"MediaPipe initialization failed"**
```
Solutions:
1. Refresh application page
2. Clear browser cache
3. Ensure stable internet connection
4. Check browser version, then upgrade browser version if necessary
5. Try different browser
6. Restart device if necessary
```

**"Session timeout"**
```
Solutions:
1. Start new session from Live Monitoring page
2. Don't minimize/inactive tab for too long
3. Ensure internet connection doesn't disconnect
4. Save important data before session ends
```

## 📜 License  
This project is intended **for educational and research purposes only**.  
Please ensure compliance with local regulations regarding student monitoring systems.  

For any use, collaboration, or deployment beyond personal/academic purposes, please contact me first before usage.

### Contact Support
- **Email Support**: its.jessicatheresia@gmail.com

## 👥 Authors & Acknowledgments

- **Developer**: Jessica Theresia
- **Institution**: Gunadarma University

### Special Thanks
- MediaPipe team for computer vision framework
- OpenCV community for image processing tools
- Railway for cloud hosting platform

## 🔄 Changelog

### v1.0.0 (Current)
- ✅ Real-time focus monitoring
- ✅ Multi-parameter detection (EAR, MAR, Iris)
- ✅ Audio/visual alerts
- ✅ Session recording & PDF reports
- ✅ File upload analysis
- ✅ Multi-person detection
- ✅ Responsive web interface
- ✅ Railway deployment

---
*Smart Focus Alert - Enhancing online learning effectiveness through AI technology* 🚀

// Manajemen Variable
let sessionStartTime = null;
let alertCount = 0;
let isMonitoring = false;
let sessionTimer = null;
let dataUpdateTimer = null;
let healthCheckTimer = null;
let lastAlertIds = new Set();
let audioEnabled = true;

let usingClientCamera = false;
let clientVideo = null;
let clientCanvas = null;
let clientCtx = null;
let clientStream = null;
let processingInterval = null;

// Real-time tracking
let clientAlerts = [];
let currentState = null;
let stateStartTime = null;
let lastAlertTime = {};
let lastReminderTime = {};
let noPersonState = {
    active: false,
    startTime: null,
    lastAlertTime: 0,
    totalDuration: 0
};

// Thresholds and cooldowns
let alertThresholds = {
    'SLEEPING': 8000,      // 8 detik  
    'YAWNING': 3500,       // 3.5 detik
    'NOT FOCUSED': 8000,   // 8 detik
    'NO PERSON': 10000     // 10 detik
};
let alertCooldown = 5000; // 5 detik

// Manajemen Sesi
let sessionId = null;
let sessionSyncTimer = null;
let fileRetryAttempts = {};
let maxRetryAttempts = 5;

let audioContext = null;
let currentDetections = [];
let systemHealth = {
    audio: 'ready',
    speech: 'ready',
    beep: 'ready'
};

// Duration tracking
let accumulatedDistractionTimes = {
    'SLEEPING': 0,
    'YAWNING': 0,
    'NOT FOCUSED': 0,
    'NO PERSON': 0
};
let totalSessionSeconds = 0;

document.addEventListener('DOMContentLoaded', function () {
    initializePage();
    setupEventListeners();
    checkCameraSetup();
    initializeAudioSystem();
    startHealthCheck();
});

function initializePage() {
    document.body.style.opacity = "0";
    document.body.style.transition = "opacity 0.6s ease";
    setTimeout(() => {
        document.body.style.opacity = "1";
    }, 100);

    clientVideo = document.getElementById('clientVideo');
    clientCanvas = document.getElementById('clientCanvas');

    if (clientCanvas) {
        clientCtx = clientCanvas.getContext('2d');
    }

    sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    console.log('Session initialized:', sessionId);
}

function initializeAudioSystem() {
    try {
        if (typeof window.AudioContext !== 'undefined') {
            audioContext = new AudioContext();
        } else if (typeof window.webkitAudioContext !== 'undefined') {
            audioContext = new webkitAudioContext();
        } else {
            console.warn('Web Audio API not supported');
            updateSystemHealth('audio', 'error');
            updateSystemHealth('beep', 'error');
            return;
        }

        if (audioContext.state === 'suspended') {
            updateSystemHealth('audio', 'ready');
        } else if (audioContext.state === 'running') {
            updateSystemHealth('audio', 'ok');
        } else {
            updateSystemHealth('audio', 'error');
        }

        if ('speechSynthesis' in window) {
            updateSystemHealth('speech', 'ready');

            speechSynthesis.onvoiceschanged = function () {
                const voices = speechSynthesis.getVoices();
                if (voices.length > 0) {
                    updateSystemHealth('speech', 'ok');
                }
            };

            speechSynthesis.getVoices();
        } else {
            console.warn('Speech Synthesis not supported');
            updateSystemHealth('speech', 'error');
        }

        updateSystemHealth('beep', 'ready');
        console.log('Audio system initialized successfully');

    } catch (error) {
        console.error('Audio initialization error:', error);
        updateSystemHealth('audio', 'error');
        updateSystemHealth('speech', 'error');
        updateSystemHealth('beep', 'error');
    }
}

function startHealthCheck() {
    healthCheckTimer = setInterval(() => {
        checkSystemHealth();
    }, 10000);
}

async function checkSystemHealth() {
    try {
        if (audioContext) {
            if (audioContext.state === 'running') {
                updateSystemHealth('audio', 'ok');
                updateSystemHealth('beep', 'ok');
            } else if (audioContext.state === 'suspended') {
                updateSystemHealth('audio', 'ready');
                updateSystemHealth('beep', 'ready');
            } else {
                updateSystemHealth('audio', 'error');
                updateSystemHealth('beep', 'error');
            }
        }

        if ('speechSynthesis' in window) {
            const voices = speechSynthesis.getVoices();
            if (voices.length > 0) {
                updateSystemHealth('speech', 'ok');
            } else {
                updateSystemHealth('speech', 'ready');
            }
        } else {
            updateSystemHealth('speech', 'error');
        }

    } catch (error) {
        console.error('Health check error:', error);
        updateSystemHealth('audio', 'error');
        updateSystemHealth('speech', 'error');
        updateSystemHealth('beep', 'error');
    }
}

function updateSystemHealth(component, status) {
    systemHealth[component] = status;

    const healthElements = {
        audio: 'audioHealth',
        speech: 'speechHealth',
        beep: 'beepHealth'
    };

    const element = document.getElementById(healthElements[component]);
    if (element) {
        element.className = `health-status ${status === 'ok' ? 'ok' : status === 'ready' ? 'ok' : 'error'}`;

        const statusText = {
            audio: {
                'ok': 'Active',
                'ready': 'Ready',
                'error': 'Error'
            },
            speech: {
                'ok': 'Active',
                'ready': 'Ready',
                'error': 'Error'
            },
            beep: {
                'ok': 'Active',
                'ready': 'Ready',
                'error': 'Error'
            }
        };

        element.textContent = statusText[component][status] || 'Unknown';
    }

    updateConnectionStatus();
}

function updateConnectionStatus() {
    const connectionIcon = document.getElementById('connectionIcon');
    const connectionSubtitle = document.getElementById('connectionSubtitle');

    const allOkOrReady = Object.values(systemHealth).every(status =>
        status === 'ok' || status === 'ready'
    );

    if (allOkOrReady) {
        connectionIcon.className = 'connection-icon';
        connectionIcon.innerHTML = '<i class="fas fa-check-circle"></i>';
        connectionSubtitle.textContent = 'Speech and beep alerts ready';
    } else {
        connectionIcon.className = 'connection-icon error';
        connectionIcon.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
        connectionSubtitle.textContent = 'Audio system has issues';
    }
}

// Audio alert functions
function playAlertSound(alertType = 'default') {
    if (!audioEnabled) return;

    try {
        if (audioContext && audioContext.state === 'suspended') {
            audioContext.resume().then(() => {
                playBeep(alertType);
            }).catch(error => {
                console.error('Audio context resume failed:', error);
                updateSystemHealth('audio', 'error');
                updateSystemHealth('beep', 'error');
            });
        } else if (audioContext && audioContext.state === 'running') {
            playBeep(alertType);
        } else {
            console.warn('Audio context not available');
            updateSystemHealth('audio', 'error');
            updateSystemHealth('beep', 'error');
        }

    } catch (error) {
        console.error('Play alert sound error:', error);
        updateSystemHealth('beep', 'error');
    }
}

function playBeep(alertType) {
    try {
        if (!audioContext || audioContext.state !== 'running') {
            throw new Error('Audio context not running');
        }

        const volume = parseFloat(document.getElementById('alertVolume').value);

        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        const frequencies = {
            'SLEEPING': 800,
            'YAWNING': 600,
            'NOT FOCUSED': 400,
            'NO PERSON': 500,
            'default': 500
        };

        oscillator.frequency.setValueAtTime(
            frequencies[alertType] || frequencies.default,
            audioContext.currentTime
        );
        oscillator.type = 'sine';

        gainNode.gain.setValueAtTime(0, audioContext.currentTime);
        gainNode.gain.linearRampToValueAtTime(volume * 0.3, audioContext.currentTime + 0.1);
        gainNode.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.6);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.6);

        updateSystemHealth('beep', 'ok');

    } catch (error) {
        console.error('Beep generation error:', error);
        updateSystemHealth('beep', 'error');
    }
}

function speakAlertMessage(message) {
    if (!audioEnabled || !window.speechSynthesis) {
        return;
    }

    try {
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(message);
        const volume = parseFloat(document.getElementById('alertVolume').value);

        utterance.volume = Math.min(volume, 1.0);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.lang = 'en-US';

        const voices = speechSynthesis.getVoices();
        if (voices.length > 0) {
            const englishVoice = voices.find(voice =>
                voice.lang.startsWith('en')
            );
            if (englishVoice) {
                utterance.voice = englishVoice;
            }
        }

        utterance.onerror = function (event) {
            console.error('Speech synthesis error:', event.error);
            updateSystemHealth('speech', 'error');
        };

        utterance.onend = function () {
            updateSystemHealth('speech', 'ok');
        };

        utterance.onstart = function () {
            updateSystemHealth('speech', 'ok');
        };

        window.speechSynthesis.speak(utterance);

    } catch (error) {
        console.error('Speech synthesis error:', error);
        updateSystemHealth('speech', 'error');
    }
}

function setupEventListeners() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', function (e) {
            if (this.getAttribute('href').startsWith('/')) {
                e.preventDefault();
                document.body.style.opacity = "0";
                setTimeout(() => {
                    window.location.href = this.getAttribute('href');
                }, 300);
            }
        });
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            if (isMonitoring) {
                stopMonitoring();
            }
        }
        if (e.key === ' ') {
            e.preventDefault();
            if (isMonitoring) {
                takeScreenshot();
            }
        }
    });

    document.getElementById('alertVolume').addEventListener('change', function () {
        showNotification(`Alert volume changed to ${this.selectedOptions[0].text}`, 'info');
    });

    document.addEventListener('click', function enableAudio() {
        if (audioContext && audioContext.state === 'suspended') {
            audioContext.resume().then(() => {
                console.log('Audio context resumed on user interaction');
                updateSystemHealth('audio', 'ok');
                updateSystemHealth('beep', 'ok');
            }).catch(error => {
                console.error('Audio context resume failed:', error);
                updateSystemHealth('audio', 'error');
                updateSystemHealth('beep', 'error');
            });
        }
        document.removeEventListener('click', enableAudio);
    });
}

function toggleAudioAlert() {
    audioEnabled = !audioEnabled;
    const toggle = document.querySelector('.toggle-switch');

    if (audioEnabled) {
        toggle.classList.remove('off');
    } else {
        toggle.classList.add('off');
    }

    updateAudioStatusText();

    if (audioEnabled) {
        setTimeout(() => {
            playAlertSound('default');
            setTimeout(() => {
                speakAlertMessage('Audio test successful');
            }, 500);
        }, 100);
    }
}

function updateAudioStatusText() {
    const statusText = document.getElementById('audioStatus');
    if (audioEnabled) {
        statusText.textContent = 'Audio alerts enabled';
        statusText.style.color = 'var(--success)';
    } else {
        statusText.textContent = 'Audio alerts disabled';
        statusText.style.color = 'var(--text-muted)';
    }
}

async function checkCameraSetup() {
    try {
        const response = await fetch('/check_camera');
        const data = await response.json();

        if (!data.camera_available) {
            usingClientCamera = true;
            document.getElementById('connectionSubtitle').textContent = 'Device camera ready for detection';
        }
    } catch (error) {
        usingClientCamera = true;
        document.getElementById('connectionSubtitle').textContent = 'Device camera';
    }
}

async function startMonitoring() {
    try {
        // Reset semua tracking variables
        clientAlerts = [];
        currentState = null;
        stateStartTime = null;
        lastAlertTime = {};
        lastReminderTime = {};
        noPersonState = {
            active: false,
            startTime: null,
            lastAlertTime: 0,
            totalDuration: 0
        };
        alertCount = 0;
        currentDetections = [];
        fileRetryAttempts = {};
        accumulatedDistractionTimes = {
            'SLEEPING': 0,
            'YAWNING': 0,
            'NOT FOCUSED': 0,
            'NO PERSON': 0
        };
        totalSessionSeconds = 0;

        const response = await fetch('/start_monitoring', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId: sessionId })
        });
        const data = await response.json();

        if (data.status !== 'success') {
            throw new Error(data.message);
        }

        if (usingClientCamera) {
            await initializeClientCamera();
        } else {
            initializeServerCamera();
        }

        updateUIForActiveMonitoring();
        startDataUpdates();
        startSessionSync();
        showNotification('Live monitoring started!', 'success');

        if (audioEnabled) {
            setTimeout(() => {
                playAlertSound('default');
                setTimeout(() => {
                    speakAlertMessage('Live monitoring started successfully');
                }, 800);
            }, 1000);
        }

    } catch (error) {
        showNotification('Failed to start monitoring: ' + error.message, 'error');
    }
}

function startSessionSync() {
    sessionSyncTimer = setInterval(() => {
        if (isMonitoring && clientAlerts.length > 0) {
            syncAlertsWithServer();
        }
    }, 30000);
}

async function syncAlertsWithServer() {
    try {
        const response = await fetch('/sync_alerts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sessionId: sessionId,
                alerts: clientAlerts
            })
        });

        const data = await response.json();
        if (data.status === 'success') {
            console.log(`Synced ${data.synced_count} alerts session`);
        }
    } catch (error) {
        console.error('Alert sync failed:', error);
    }
}

async function initializeClientCamera() {
    try {
        clientStream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' }
        });

        clientVideo.srcObject = clientStream;
        await new Promise((resolve) => {
            clientVideo.onloadedmetadata = resolve;
        });

        clientVideo.style.display = 'none';
        clientCanvas.style.display = 'block';

        processingInterval = setInterval(processClientFrame, 1000);

    } catch (error) {
        throw new Error('Failed to access device camera: ' + error.message);
    }
}

function initializeServerCamera() {
    document.getElementById('videoStream').src = '/video_feed';
    document.getElementById('videoStream').style.display = 'block';
}

function processClientFrame() {
    if (!clientVideo || !isMonitoring || !clientStream) return;

    try {
        clientCtx.drawImage(clientVideo, 0, 0, clientCanvas.width, clientCanvas.height);

        const frameData = clientCanvas.toDataURL('image/jpeg', 0.7);

        fetch('/process_frame', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                frame: frameData,
                sessionId: sessionId,
                timestamp: Date.now()
            })
        })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.processed_frame) {
                    const img = new Image();
                    img.onload = function () {
                        clientCtx.drawImage(img, 0, 0, clientCanvas.width, clientCanvas.height);
                    };
                    img.src = data.processed_frame;

                    // Proses hanya single person
                    if (data.detections && data.detections.length > 0) {
                        // Hanya proses orang pertama terdeteksi
                        const detection = data.detections[0];
                        processDetectionAlerts([detection]);
                    } else {
                        handleNoPersonDetection();
                    }
                }
            })
            .catch(error => {
                console.error('Frame processing error:', error);
            });

    } catch (error) {
        console.error('Frame capture error:', error);
    }
}

// NO PERSON penanganan deteksi
function handleNoPersonDetection() {
    const currentTime = Date.now();

    // Reset person state sejak tidak ada person terdeteksi
    if (currentState && alertThresholds[currentState] && stateStartTime) {
        const stateDuration = (currentTime - stateStartTime) / 1000;
        if (stateDuration > 0) {
            accumulatedDistractionTimes[currentState] += stateDuration;
        }
    }

    currentState = null;
    stateStartTime = null;
    lastAlertTime = {};
    lastReminderTime = {};

    // Handle NO PERSON state
    if (!noPersonState.active) {
        noPersonState.active = true;
        noPersonState.startTime = currentTime;
        console.log('Started NO PERSON tracking');
    } else {
        const duration = currentTime - noPersonState.startTime;
        const threshold = alertThresholds['NO PERSON'];

        if (duration >= threshold) {
            const lastAlert = noPersonState.lastAlertTime || 0;

            if (lastAlert === 0) {
                // NO PERSON alert pertama
                triggerClientAlert('NO PERSON', Math.floor(duration / 1000), 'initial');
                noPersonState.lastAlertTime = currentTime;
                console.log(`First NO PERSON alert after ${duration}ms`);
            } else if (currentTime - lastAlert >= alertCooldown) {
                // Reminder NO PERSON alert
                triggerClientAlert('NO PERSON', Math.floor(duration / 1000), 'reminder');
                noPersonState.lastAlertTime = currentTime;
                console.log(`Reminder NO PERSON alert (${duration}ms total)`);
            }
        }
    }

    // Update UI to show NO PERSON state
    currentDetections = [];
    updateDetectionDisplayForNoPerson();
    updateUIWithNoPersonDetection();
}

function resetNoPersonState() {
    if (noPersonState.active) {
        const currentTime = Date.now();
        const duration = (currentTime - noPersonState.startTime) / 1000;
        if (duration > 0) {
            noPersonState.totalDuration += duration;
            accumulatedDistractionTimes['NO PERSON'] += duration;
        }

        noPersonState = {
            active: false,
            startTime: null,
            lastAlertTime: 0,
            totalDuration: noPersonState.totalDuration
        };
        console.log(`Reset NO PERSON state, accumulated: ${noPersonState.totalDuration}s`);
    }
}

function processDetectionAlerts(detections) {
    const currentTime = Date.now();
    currentDetections = detections;

    // Reset NO PERSON state ketika person terdeteksi
    resetNoPersonState();

    // Hanya proses person pertama
    const detection = detections[0];
    const newState = detection.status;

    if (!stateStartTime) {
        stateStartTime = currentTime;
        lastAlertTime = {};
        lastReminderTime = {};
    }

    if (currentState !== newState) {
        const previousState = currentState;
        if (previousState && alertThresholds[previousState] && stateStartTime) {
            const stateDuration = (currentTime - stateStartTime) / 1000;
            if (stateDuration > 0) {
                accumulatedDistractionTimes[previousState] += stateDuration;
            }
        }

        currentState = newState;
        stateStartTime = currentTime;

        lastAlertTime = {};
        lastReminderTime = {};

    } else {
        if (alertThresholds[currentState] && stateStartTime) {
            const duration = currentTime - stateStartTime;
            const thresholdMs = alertThresholds[currentState];

            if (duration >= thresholdMs) {
                const lastAlert = lastAlertTime[currentState] || 0;

                if (lastAlert === 0) {
                    triggerClientAlert(currentState, Math.floor(duration / 1000), 'initial');
                    lastAlertTime[currentState] = currentTime;
                    lastReminderTime[currentState] = currentTime;
                } else {
                    const lastReminder = lastReminderTime[currentState] || 0;
                    if (currentTime - lastReminder >= alertCooldown) {
                        triggerClientAlert(currentState, Math.floor(duration / 1000), 'reminder');
                        lastReminderTime[currentState] = currentTime;
                    }
                }
            }
        }
    }

    updateUIWithDetections(detections);
    updateDetectionDisplay();
}

function updateDetectionDisplayForNoPerson() {
    const detectionInfo = document.getElementById('detectionInfo');
    const detectionBadge = document.getElementById('detectionBadge');
    const currentTime = Date.now();

    if (noPersonState.active) {
        const duration = (currentTime - noPersonState.startTime) / 1000;
        const threshold = alertThresholds['NO PERSON'] / 1000;
        const progressPercent = Math.min(100, (duration / threshold) * 100);
        const showAlert = duration >= threshold;

        const alertBadgeHtml = showAlert ? '<span class="alert-badge"><i class="fas fa-exclamation-triangle"></i>ALERT</span>' : '';

        detectionInfo.innerHTML = `
                    <div class="detection-item no-person">
                        <div class="detection-details">
                            <div class="detection-person">
                                No Person Detected
                                ${alertBadgeHtml}
                            </div>
                            <div class="detection-status">NO PERSON</div>
                        </div>
                        <div class="detection-timer-section">
                            <div class="detection-timer no-person">${duration.toFixed(1)}s / ${threshold}s</div>
                            <div class="detection-progress">
                                <div class="detection-progress-bar no-person" style="width: ${progressPercent}%"></div>
                            </div>
                            <div class="threshold-text">Tracking</div>
                        </div>
                    </div>
                `;

        detectionBadge.style.display = showAlert ? 'inline-flex' : 'none';
    } else {
        detectionInfo.innerHTML = '<div class="text-center" style="color: var(--text-secondary); padding: 20px;"><i class="fas fa-search" style="font-size: 2rem; margin-bottom: 12px; display: block;"></i><p>No person detected in frame</p></div>';
        detectionBadge.style.display = 'none';
    }
}

function updateDetectionDisplay() {
    const detectionInfo = document.getElementById('detectionInfo');
    const detectionBadge = document.getElementById('detectionBadge');

    if (currentDetections.length === 0) {
        updateDetectionDisplayForNoPerson();
        return;
    }

    let hasActiveAlert = false;
    const currentTime = Date.now();

    // Hanya Tampilkan Single Person
    const detection = currentDetections[0];
    const stateClass = currentState ? currentState.toLowerCase().replace(' ', '-') : 'focused';

    let timerDisplay = '';
    let progressPercent = 0;
    let showAlert = false;

    if (alertThresholds[currentState] && stateStartTime) {
        const duration = Math.max(0, currentTime - stateStartTime);
        const threshold = alertThresholds[currentState];
        const durationSeconds = Math.floor(duration / 1000);
        const thresholdSeconds = Math.floor(threshold / 1000);

        progressPercent = Math.min(100, (duration / threshold) * 100);
        timerDisplay = `${durationSeconds}s / ${thresholdSeconds}s`;

        if (duration >= threshold) {
            showAlert = true;
            hasActiveAlert = true;
        }
    } else if (currentState === 'FOCUSED') {
        timerDisplay = 'FOCUSED';
        progressPercent = 0;
    } else {
        const threshold = alertThresholds[currentState] || 1000;
        const thresholdSeconds = Math.floor(threshold / 1000);
        timerDisplay = `0s / ${thresholdSeconds}s`;
        progressPercent = 0;
    }

    const detectionHTML = `
                <div class="detection-item ${stateClass}">
                    <div class="detection-details">
                        <div class="detection-person">
                            Status
                            ${showAlert ? '<span class="alert-badge"><i class="fas fa-exclamation-triangle"></i>ALERT</span>' : ''}
                        </div>
                        <div class="detection-status">${currentState || 'FOCUSED'}</div>
                        <div class="detection-confidence">Confidence: ${(detection.confidence * 100).toFixed(1)}%</div>
                    </div>
                    <div class="detection-timer-section">
                        <div class="detection-timer ${stateClass}">${timerDisplay}</div>
                        ${currentState !== 'FOCUSED' ? `
                            <div class="detection-progress">
                                <div class="detection-progress-bar ${stateClass}" style="width: ${progressPercent}%"></div>
                            </div>
                            <div class="threshold-text">Tracking</div>
                        ` : ''}
                    </div>
                </div>
            `;

    detectionInfo.innerHTML = detectionHTML;
    detectionBadge.style.display = hasActiveAlert ? 'inline-flex' : 'none';
}

function triggerClientAlert(alertType, duration, alertCategory) {
    const alertTime = new Date().toLocaleTimeString();
    const alertMessage = getAlertMessage(alertType);

    const alert = {
        id: `${sessionId}_${alertType}_${Date.now()}`,
        time: alertTime,
        person: alertType === 'NO PERSON' ? 'System' : 'You',
        detection: alertType,
        message: alertMessage,
        duration: duration,
        type: alertType === 'SLEEPING' || alertType === 'NO PERSON' ? 'error' : 'warning',
        sessionId: sessionId,
        timestamp: new Date().toISOString(),
        category: alertCategory,
        is_reminder: alertCategory === 'reminder'
    };

    clientAlerts.unshift(alert);

    if (clientAlerts.length > 100) {
        clientAlerts = clientAlerts.slice(0, 100);
    }

    alertCount++;
    document.getElementById('alertCount').textContent = alertCount;

    if (audioEnabled) {
        playAlertSound(alertType);

        setTimeout(() => {
            speakAlertMessage(getSpeechMessage(alertType));
        }, 300);
    }

    updateClientAlertHistory();
    showNotification(alertMessage, alert.type);
}

function getAlertMessage(alertType) {
    const baseMessages = {
        'SLEEPING': 'You are sleeping, please wake up!',
        'YAWNING': 'You are yawning, please take a rest!',
        'NOT FOCUSED': 'You are not focused, please focus on screen!',
        'NO PERSON': 'No person detected. Please position yourself in front of the camera!'
    };

    return baseMessages[alertType] || 'Attention alert';
}

function getSpeechMessage(alertType) {
    const speechMessages = {
        'SLEEPING': 'You are sleeping. Please wake up!',
        'YAWNING': 'You are yawning. Please take a rest!',
        'NOT FOCUSED': 'You are not focused. Please pay attention!',
        'NO PERSON': 'No person detected. Please position yourself in front of the camera!'
    };

    return speechMessages[alertType] || 'Attention alert';
}

function updateUIWithDetections(detections) {
    // always show max 1 person
    document.getElementById('personDetected').textContent = detections.length > 0 ? 1 : 0;

    const focusedCount = detections.length > 0 && detections[0].status === 'FOCUSED' ? 1 : 0;
    document.getElementById('focusedState').textContent = focusedCount;

    let overallStatus = 'FOCUSED';
    if (detections.length > 0) {
        overallStatus = detections[0].status;
    }

    updateCurrentStatus(overallStatus);
}

function updateUIWithNoPersonDetection() {
    document.getElementById('personDetected').textContent = 0;
    document.getElementById('focusedState').textContent = 0;
    updateCurrentStatus('NO PERSON');
}

function updateClientAlertHistory() {
    const alertHistory = document.getElementById('alertHistory');

    if (clientAlerts.length === 0) {
        alertHistory.innerHTML = '<div class="text-center" style="color: var(--text-secondary); padding: 20px;"><i class="fas fa-clock" style="font-size: 2rem; margin-bottom: 12px; display: block;"></i><p>No alerts yet in this session.</p></div>';
        return;
    }

    alertHistory.innerHTML = clientAlerts.slice(0, 15).map(alert => {
        const borderColor = alert.type === 'error' ? 'var(--danger)' :
            alert.detection === 'NO PERSON' ? 'var(--no-person)' : 'var(--warning)';

        return `<div class="alert-item" style="border-left-color: ${borderColor};">
                    <div style="flex: 1;">
                        <div style="font-weight: 500; margin-bottom: 4px;">${alert.message}</div>
                        <div style="font-size: 0.8rem; color: var(--text-muted);">Duration: ${alert.duration}s</div>
                    </div>
                    <div class="alert-time">${alert.time}</div>
                    <div class="alert-duration">${alert.duration}s</div>
                </div>`;
    }).join('');
}

async function stopMonitoring() {
    try {
        // Kalkulasi akumulasi waktu final
        const currentTime = Date.now();
        if (currentState && alertThresholds[currentState] && stateStartTime) {
            const stateDuration = (currentTime - stateStartTime) / 1000;
            if (stateDuration > 0) {
                accumulatedDistractionTimes[currentState] += stateDuration;
            }
        }

        // Finalisasi NO PERSON state
        if (noPersonState.active && noPersonState.startTime) {
            const noPersonDuration = (currentTime - noPersonState.startTime) / 1000;
            if (noPersonDuration > 0) {
                noPersonState.totalDuration += noPersonDuration;
                accumulatedDistractionTimes['NO PERSON'] += noPersonDuration;
            }
        }

        if (sessionStartTime) {
            totalSessionSeconds = (currentTime - sessionStartTime) / 1000;
        }

        const stopData = {
            sessionId: sessionId,
            alerts: clientAlerts,
            totalAlerts: alertCount,
            sessionDuration: totalSessionSeconds,
            accumulatedDistractionTimes: accumulatedDistractionTimes,
            noPersonState: noPersonState,
            detectionStats: {
                totalDetections: currentDetections.length,
                alertsGenerated: clientAlerts.length
            }
        };

        const response = await fetch('/stop_monitoring', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(stopData)
        });
        const data = await response.json();

        updateUIForInactiveMonitoring();
        stopDataUpdates();
        stopSessionSync();

        if (clientStream) {
            clientStream.getTracks().forEach(track => track.stop());
            clientStream = null;
        }

        if (processingInterval) {
            clearInterval(processingInterval);
            processingInterval = null;
        }

        // Reset tracking
        currentState = null;
        stateStartTime = null;
        lastAlertTime = {};
        lastReminderTime = {};
        noPersonState = {
            active: false,
            startTime: null,
            lastAlertTime: 0,
            totalDuration: 0
        };
        currentDetections = [];
        updateDetectionDisplay();

        showNotification(`Session complete! Generated ${alertCount} alerts`, 'success');

        if (audioEnabled) {
            setTimeout(() => {
                speakAlertMessage(`Session completed. ${alertCount} alerts generated.`);
            }, 500);
        }

        setTimeout(() => {
            attemptFileDownloadWithRetry(data);
        }, 3000);

    } catch (error) {
        showNotification('Failed to stop monitoring: ' + error.message, 'error');
    }
}

function stopSessionSync() {
    if (sessionSyncTimer) {
        clearInterval(sessionSyncTimer);
        sessionSyncTimer = null;
    }
}

async function attemptFileDownloadWithRetry(data, attempt = 1) {
    let pdfUrl = data.pdf_report;
    let videoUrl = data.video_file;

    if (!pdfUrl || !videoUrl) {
        if (attempt < maxRetryAttempts) {
            showNotification(`Files are being generated (attempt ${attempt}/${maxRetryAttempts}). Please wait...`, 'info');

            setTimeout(async () => {
                try {
                    const checkResponse = await fetch('/health');
                    const healthData = await checkResponse.json();

                    const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '_');
                    const possiblePdfUrls = [
                        `/static/reports/session_report_${timestamp}.pdf`,
                        `/static/reports/session_report_latest.pdf`,
                        data.pdf_report
                    ].filter(url => url);

                    const possibleVideoUrls = [
                        `/static/recordings/session_recording_${timestamp}.mp4`,
                        `/static/recordings/session_recording_latest.mp4`,
                        data.video_file
                    ].filter(url => url);

                    for (const url of possiblePdfUrls) {
                        try {
                            const testResponse = await fetch(url, { method: 'HEAD' });
                            if (testResponse.ok) {
                                pdfUrl = url;
                                break;
                            }
                        } catch (e) { }
                    }

                    for (const url of possibleVideoUrls) {
                        try {
                            const testResponse = await fetch(url, { method: 'HEAD' });
                            if (testResponse.ok) {
                                videoUrl = url;
                                break;
                            }
                        } catch (e) { }
                    }

                    const newData = { pdf_report: pdfUrl, video_file: videoUrl };
                    attemptFileDownloadWithRetry(newData, attempt + 1);

                } catch (error) {
                    attemptFileDownloadWithRetry(data, attempt + 1);
                }
            }, attempt * 5000);

            return;
        } else {
            showNotification('Maximum retry attempts reached. Files may be available later.', 'warning');
            return;
        }
    }

    if (pdfUrl || videoUrl) {
        showDownloads(pdfUrl, videoUrl);
        showNotification('Files generated successfully!', 'success');
    } else {
        showNotification('File generation failed.', 'error');
    }
}

function updateUIForInactiveMonitoring() {
    isMonitoring = false;

    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;

    const liveIndicator = document.getElementById('liveIndicator');
    const liveDot = document.getElementById('liveDot');
    const liveText = document.getElementById('liveText');

    liveIndicator.classList.remove('active');
    liveDot.classList.remove('active');
    liveText.textContent = 'READY';

    document.getElementById('videoStream').style.display = 'none';
    document.getElementById('videoStream').src = '';
    document.getElementById('clientVideo').style.display = 'none';
    document.getElementById('clientCanvas').style.display = 'none';
    document.getElementById('videoPlaceholder').style.display = 'block';

    updateCurrentStatus('READY');

    if (sessionTimer) {
        clearInterval(sessionTimer);
        sessionTimer = null;
    }

    document.getElementById('personDetected').textContent = '0';
    document.getElementById('focusedState').textContent = '0';

    const detectionInfo = document.getElementById('detectionInfo');
    detectionInfo.innerHTML = '<div class="text-center" style="color: var(--text-secondary); padding: 20px;"><i class="fas fa-search" style="font-size: 2rem; margin-bottom: 12px; display: block;"></i><p>Detection system ready</p></div>';

    const detectionBadge = document.getElementById('detectionBadge');
    detectionBadge.style.display = 'none';
}

function updateUIForActiveMonitoring() {
    isMonitoring = true;
    sessionStartTime = Date.now();

    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;

    const liveIndicator = document.getElementById('liveIndicator');
    const liveDot = document.getElementById('liveDot');
    const liveText = document.getElementById('liveText');

    liveIndicator.classList.add('active');
    liveDot.classList.add('active');
    liveText.textContent = 'LIVE';

    document.getElementById('videoPlaceholder').style.display = 'none';

    updateCurrentStatus('READY');
    startSessionTimer();

    const alertHistory = document.getElementById('alertHistory');
    alertHistory.innerHTML = '<div class="text-center" style="color: var(--text-secondary); padding: 20px;"><i class="fas fa-clock" style="font-size: 2rem; margin-bottom: 12px; display: block;"></i><p>Monitoring started...</p></div>';

    const detectionInfo = document.getElementById('detectionInfo');
    detectionInfo.innerHTML = '<div class="text-center" style="color: var(--text-secondary); padding: 20px;"><i class="fas fa-search" style="font-size: 2rem; margin-bottom: 12px; display: block;"></i><p>Monitoring active...</p></div>';

    lastAlertIds.clear();
}

function startDataUpdates() {
    dataUpdateTimer = setInterval(() => {
        if (isMonitoring && !usingClientCamera) {
            fetch('/get_monitoring_data')
                .then(response => response.json())
                .then(data => {
                    if (!data.error) {
                        updateMonitoringDisplay(data);
                        updateAlerts(data.latest_alerts || []);
                    }
                })
                .catch(error => {
                    console.error('Failed to fetch monitoring data:', error);
                });
        }
    }, 3000);
}

function stopDataUpdates() {
    if (dataUpdateTimer) {
        clearInterval(dataUpdateTimer);
        dataUpdateTimer = null;
    }
}

function updateMonitoringDisplay(data) {
    document.getElementById('personDetected').textContent = Math.min(1, data.total_persons || 0);
    document.getElementById('focusedState').textContent = Math.min(1, data.focused_count || 0);
    document.getElementById('alertCount').textContent = data.alert_count || 0;

    const currentStatus = data.current_status || 'READY';
    updateCurrentStatus(currentStatus);
}

function updateCurrentStatus(status) {
    const statusElement = document.getElementById('currentStatus');
    const statusClasses = ['status-ready', 'status-focused', 'status-unfocused', 'status-yawning', 'status-sleeping', 'status-no-person'];

    statusClasses.forEach(cls => statusElement.classList.remove(cls));

    let statusClass, message;
    switch (status) {
        case 'FOCUSED':
            statusClass = 'status-focused';
            message = 'Focused';
            break;
        case 'NOT FOCUSED':
            statusClass = 'status-unfocused';
            message = 'Attention drift detected';
            break;
        case 'YAWNING':
            statusClass = 'status-yawning';
            message = 'Fatigue signs detected';
            break;
        case 'SLEEPING':
            statusClass = 'status-sleeping';
            message = 'Sleep detected';
            break;
        case 'NO PERSON':
            statusClass = 'status-no-person';
            message = 'No person detected';
            break;
        default:
            statusClass = 'status-ready';
            message = 'Monitoring ready';
    }

    statusElement.classList.add(statusClass);
    statusElement.innerHTML = `
                <span class="status-indicator ${statusClass.replace('status-', 'status-')}"></span>
                ${message}
            `;
}

function updateAlerts(alerts) {
    if (usingClientCamera) return;

    const alertHistory = document.getElementById('alertHistory');

    if (alerts.length === 0) {
        alertHistory.innerHTML = '<div class="text-center" style="color: var(--text-secondary); padding: 20px;"><i class="fas fa-clock" style="font-size: 2rem; margin-bottom: 12px; display: block;"></i><p>No recent alerts.</p></div>';
        return;
    }

    alertHistory.innerHTML = alerts.map(alert => {
        const borderColor = alert.type === 'error' ? 'var(--danger)' :
            alert.detection === 'NO PERSON' ? 'var(--no-person)' : 'var(--warning)';

        return `<div class="alert-item" style="border-left-color: ${borderColor};">
                    <div style="flex: 1;">
                        <div style="font-weight: 500; margin-bottom: 4px;">${alert.message}</div>
                        <div style="font-size: 0.8rem; color: var(--text-muted);">Duration: ${alert.duration || 0}s</div>
                    </div>
                    <div class="alert-time">${alert.time}</div>
                </div>`;
    }).join('');
}

function startSessionTimer() {
    sessionTimer = setInterval(() => {
        if (sessionStartTime && isMonitoring) {
            const elapsed = Date.now() - sessionStartTime;
            const hours = Math.floor(elapsed / 3600000);
            const minutes = Math.floor((elapsed % 3600000) / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);
            document.getElementById('sessionTime').textContent =
                `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }
    }, 1000);
}

function showDownloads(pdfReport, videoFile) {
    const downloadsSection = document.getElementById('downloadsSection');
    const downloadItems = document.getElementById('downloadItems');

    downloadItems.innerHTML = '';

    if (pdfReport) {
        const pdfItem = document.createElement('div');
        pdfItem.className = 'download-item';
        pdfItem.innerHTML = `
                    <div class="download-info">
                        <div class="file-icon">
                            <i class="fas fa-file-pdf"></i>
                        </div>
                        <div>
                            <div style="font-weight: 600;">Session Report</div>
                            <div style="color: var(--text-secondary); font-size: 0.9rem;">PDF with ${alertCount} alerts.</div>
                        </div>
                    </div>
                    <a href="${pdfReport}" download class="btn btn-primary">
                        <i class="fas fa-download"></i>
                    </a>
                `;
        downloadItems.appendChild(pdfItem);
    }

    if (videoFile) {
        const videoItem = document.createElement('div');
        videoItem.className = 'download-item';
        videoItem.innerHTML = `
                    <div class="download-info">
                        <div class="file-icon">
                            <i class="fas fa-video"></i>
                        </div>
                        <div>
                            <div style="font-weight: 600;">Session Recording</div>
                            <div style="color: var(--text-secondary); font-size: 0.9rem;">Video detection overlay</div>
                        </div>
                    </div>
                    <a href="${videoFile}" download class="btn btn-secondary">
                        <i class="fas fa-download"></i>
                    </a>
                `;
        downloadItems.appendChild(videoItem);
    }

    downloadsSection.style.display = 'block';
}

function takeScreenshot() {
    if (clientCanvas && isMonitoring) {
        try {
            const link = document.createElement('a');
            link.download = `single_person_screenshot_${sessionId}_${Date.now()}.png`;
            link.href = clientCanvas.toDataURL();
            link.click();
            showNotification('Screenshot captured', 'success');
        } catch (error) {
            showNotification('Screenshot failed', 'error');
        }
    } else {
        showNotification('Screenshot captured successfully', 'success');
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: var(--glass-bg);
                border: 1px solid var(--glass-border);
                border-radius: 8px;
                padding: 16px;
                color: var(--text-primary);
                z-index: 1000;
                max-width: 350px;
                animation: slideInRight 0.3s ease-out;
                backdrop-filter: blur(10px);
            `;

    const colors = {
        success: 'var(--success)',
        warning: 'var(--warning)',
        error: 'var(--danger)',
        info: 'var(--info)'
    };

    const icons = {
        success: 'fa-check-circle',
        warning: 'fa-exclamation-triangle',
        error: 'fa-times-circle',
        info: 'fa-info-circle'
    };

    notification.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="fas ${icons[type] || icons.info}" style="color: ${colors[type] || colors.info};"></i>
                    <span>${message}</span>
                    <button onclick="this.parentElement.parentElement.remove()" 
                            style="background: none; border: none; color: var(--text-secondary); cursor: pointer; margin-left: auto;">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;

    document.body.appendChild(notification);

    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 8000);
}

// Bersihkan Halaman Tidak ter-load
window.addEventListener('beforeunload', function () {
    if (isMonitoring) {
        fetch('/stop_monitoring', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sessionId: sessionId,
                alerts: clientAlerts,
                emergencyStop: true,
                accumulatedDistractionTimes: accumulatedDistractionTimes,
                noPersonState: noPersonState
            }),
            keepalive: true
        }).catch(() => { });
    }

    if (clientStream) {
        clientStream.getTracks().forEach(track => track.stop());
    }
    if (healthCheckTimer) clearInterval(healthCheckTimer);
    if (dataUpdateTimer) clearInterval(dataUpdateTimer);
    if (sessionTimer) clearInterval(sessionTimer);
    if (processingInterval) clearInterval(processingInterval);
    if (sessionSyncTimer) clearInterval(sessionSyncTimer);
});

document.addEventListener('visibilitychange', function () {
    if (document.hidden && isMonitoring) {
        if (processingInterval) {
            clearInterval(processingInterval);
            processingInterval = setInterval(processClientFrame, 3000);
        }
    } else if (!document.hidden && isMonitoring) {
        if (processingInterval) {
            clearInterval(processingInterval);
            processingInterval = setInterval(processClientFrame, 1000);
        }
    }
});

setInterval(() => {
    if (isMonitoring && clientAlerts.length > 50) {
        clientAlerts = clientAlerts.slice(0, 50);
    }
}, 60000);

// Initialize audio status text
updateAudioStatusText();
// Global variables
let selectedFile = null;
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const fileInfo = document.getElementById("fileInfo");
const analyzeBtn = document.getElementById("analyzeBtn");
const uploadProgress = document.getElementById("uploadProgress");
const progressFill = document.getElementById("progressFill");
const progressPercent = document.getElementById("progressPercent");

// Initialize page
document.addEventListener("DOMContentLoaded", function () {
  initializePage();
  setupEventListeners();
});

function initializePage() {
  // Page load animation
  document.body.style.opacity = "0";
  document.body.style.transition = "opacity 0.6s ease";
  setTimeout(() => {
    document.body.style.opacity = "1";
  }, 100);
}

function setupEventListeners() {
  // Fungsi Drag and drop
  dropZone.addEventListener("dragover", handleDragOver);
  dropZone.addEventListener("dragleave", handleDragLeave);
  dropZone.addEventListener("drop", handleDrop);
  dropZone.addEventListener("click", () => fileInput.click());

  // File input
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleFileSelect(e.target.files[0]);
    }
  });

  // Form submission
  document
    .getElementById("uploadForm")
    .addEventListener("submit", handleFormSubmit);

  // Navigation links
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.addEventListener("click", function (e) {
      if (this.getAttribute("href").startsWith("/")) {
        e.preventDefault();
        document.body.style.opacity = "0";
        setTimeout(() => {
          window.location.href = this.getAttribute("href");
        }, 300);
      }
    });
  });

  // Button hover effects
  document.querySelectorAll(".btn").forEach((button) => {
    button.addEventListener("mouseenter", function () {
      if (!this.disabled) {
        this.style.transform = "translateY(-3px) scale(1.05)";
      }
    });

    button.addEventListener("mouseleave", function () {
      this.style.transform = "translateY(0) scale(1)";
    });
  });
}

function handleDragOver(e) {
  e.preventDefault();
  dropZone.classList.add("dragover");
}

function handleDragLeave(e) {
  e.preventDefault();
  dropZone.classList.remove("dragover");
}

function handleDrop(e) {
  e.preventDefault();
  dropZone.classList.remove("dragover");

  const files = e.dataTransfer.files;
  if (files.length > 0) {
    handleFileSelect(files[0]);
  }
}

function handleFileSelect(file) {
  // Validasi tipe file
  const validTypes = [
    "image/jpeg", "image/jpg", "image/png", "image/bmp", 
    "video/mp4", "video/avi", "video/mov", "video/quicktime","video/x-msvideo","video/x-matroska"
  ];

  if (!validTypes.includes(file.type)) {
    showError(
      "Please select a valid image (JPG, PNG, BMP) or video file (MP4, AVI, MOV, MKV)"
    );
    return;
  }

  // Validasi ukuran (100MB limit)
  if (file.size > 100 * 1024 * 1024) {
    showError("File size must be less than 100MB");
    return;
  }

  selectedFile = file;

  // Info File
  document.getElementById("fileName").textContent = file.name;
  document.getElementById("fileSize").textContent = formatFileSize(file.size);
  document.getElementById("fileType").textContent = file.type;

  // Preview
  if (file.type.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = (e) => {
      document.getElementById("filePreview").src = e.target.result;
      document.getElementById("filePreview").style.display = "block";
      document.getElementById("videoPreview").style.display = "none";
    };
    reader.readAsDataURL(file);
  } else {
    document.getElementById("filePreview").style.display = "none";
    document.getElementById("videoPreview").style.display = "block";
  }

  fileInfo.style.display = "block";
  analyzeBtn.disabled = false;
  hideMessages();

  showSuccess(`File "${file.name}" selected successfully. Ready for analysis with PDF report generation.`);
}

function handleFormSubmit(e) {
  e.preventDefault();

  if (!selectedFile) {
    showError("Please select a file first");
    return;
  }

  // Tampilkan progress
  uploadProgress.style.display = "block";
  analyzeBtn.disabled = true;
  analyzeBtn.innerHTML =
    '<i class="fas fa-spinner fa-spin" style="margin-right: 8px;"></i>Analyzing & Generating Report...';

  // Simulasi progress
  simulateProgress();

  // BUat FormData
  const formData = new FormData();
  formData.append("file", selectedFile);

  // Submit form ke backend
  fetch("/upload", {
    method: "POST",
    body: formData,
  })
    .then((response) => {
      if (response.ok) {
        return response.text();
      } else {
        throw new Error("Upload failed");
      }
    })
    .then((html) => {
      // Handle success - replace page content or redirect to results
      document.body.innerHTML = html;
      window.history.pushState({}, "", "/results");
    })
    .catch((error) => {
      console.error("Error:", error);
      showError("Upload failed. Please try again.");
      resetUploadState();
    });
}

function simulateProgress() {
  let progress = 0;
  const interval = setInterval(() => {
    progress += Math.random() * 10;
    if (progress > 95) progress = 95;

    progressFill.style.width = progress + "%";
    progressPercent.textContent = Math.round(progress) + "%";

    if (progress >= 95) {
      clearInterval(interval);
    }
  }, 200);
}

function resetUploadState() {
  uploadProgress.style.display = "none";
  analyzeBtn.disabled = false;
  analyzeBtn.innerHTML =
    '<i class="fas fa-search" style="margin-right: 8px;"></i>Analyze & Generate Report';
  progressFill.style.width = "0%";
  progressPercent.textContent = "0%";
}

function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function showError(message) {
  document.getElementById("errorText").textContent = message;
  document.getElementById("errorMessage").style.display = "flex";
  document.getElementById("successMessage").style.display = "none";
}

function showSuccess(message) {
  document.getElementById("successText").textContent = message;
  document.getElementById("successMessage").style.display = "flex";
  document.getElementById("errorMessage").style.display = "none";

  // Auto hide success message
  setTimeout(() => {
    document.getElementById("successMessage").style.display = "none";
  }, 4000);
}

function hideMessages() {
  document.getElementById("errorMessage").style.display = "none";
  document.getElementById("successMessage").style.display = "none";
}

// Keyboard shortcuts
document.addEventListener("keydown", function (e) {
  if (e.ctrlKey && e.key === "o") {
    e.preventDefault();
    fileInput.click();
  }
});

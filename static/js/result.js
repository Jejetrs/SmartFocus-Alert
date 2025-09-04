// Inisialisasi animations
document.body.style.opacity = "0";
document.body.style.transition = "opacity 0.5s";

window.addEventListener("load", function () {
  document.body.style.opacity = "1";
});

// Navigation dengan transisi smooth
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
    this.style.transform = "translateY(-3px) scale(1.05)";
  });

  button.addEventListener("mouseleave", function () {
    this.style.transform = "translateY(0) scale(1)";
  });
});

// Card hover animations
document.querySelectorAll(".person-card").forEach((card) => {
  card.addEventListener("mouseenter", function () {
    this.style.transform = "translateY(-8px) scale(1.02)";
  });

  card.addEventListener("mouseleave", function () {
    this.style.transform = "translateY(0) scale(1)";
  });
});

// Pemantauan performance
window.addEventListener("load", function () {
  const perfData = performance.getEntriesByType("navigation")[0];
  if (perfData) {
    const loadTime = perfData.loadEventEnd - perfData.fetchStart;
    console.log(`Results page loaded in ${loadTime}ms`);
  }
});

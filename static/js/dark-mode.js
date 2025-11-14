// Dark Mode Toggle for VisionCart

// Initialize theme from localStorage or default to light
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateToggleButton(savedTheme);
}

// Toggle between light and dark mode
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateToggleButton(newTheme);
    
    // Optional: Add a little celebration effect
    celebrateToggle();
}

// Update toggle button icon
function updateToggleButton(theme) {
    const toggleBtn = document.getElementById('themeToggle');
    if (toggleBtn) {
        toggleBtn.innerHTML = theme === 'light' ? '🌙' : '☀️';
        toggleBtn.setAttribute('aria-label', 
            theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'
        );
    }
}

// Optional: Celebration effect when toggling
function celebrateToggle() {
    const toggleBtn = document.getElementById('themeToggle');
    if (toggleBtn) {
        toggleBtn.style.animation = 'none';
        setTimeout(() => {
            toggleBtn.style.animation = 'spin 0.5s ease-in-out';
        }, 10);
    }
}

// Add CSS animation for button spin
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        0% { transform: rotate(0deg) scale(1); }
        50% { transform: rotate(180deg) scale(1.2); }
        100% { transform: rotate(360deg) scale(1); }
    }
`;
document.head.appendChild(style);

// Initialize theme on page load
document.addEventListener('DOMContentLoaded', initTheme);

// Export functions for use in other scripts
window.toggleTheme = toggleTheme;
window.initTheme = initTheme;
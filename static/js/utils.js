/**
 * Shared frontend utilities for Zentrol.
 *
 * Load this script before gesture_engine.js and presentation.js so the
 * helpers are available as module-level globals.
 */

/**
 * Read the Django CSRF token.
 * Checks the hidden form input first, then falls back to the csrftoken cookie.
 * @returns {string}
 */
function getCsrfToken() {
    const fromInput = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (fromInput) return fromInput;

    for (const cookie of document.cookie.split(';')) {
        const [key, value] = cookie.trim().split('=');
        if (key === 'csrftoken') return decodeURIComponent(value);
    }

    return '';
}

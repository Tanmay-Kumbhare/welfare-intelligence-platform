import "@testing-library/jest-dom/vitest";

// jsdom defines window.scrollTo as a not-implemented stub that logs errors;
// replace it unconditionally with a quiet no-op.
window.scrollTo = () => {};

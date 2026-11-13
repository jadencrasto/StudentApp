import '@testing-library/jest-dom';

// JSDOM doesn't implement window.scrollTo
if (typeof window !== 'undefined') {
  window.scrollTo = () => {};
}

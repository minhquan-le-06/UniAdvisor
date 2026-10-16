import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

// jsdom has no layout: scrolling and media queries are no-ops in tests.
Element.prototype.scrollIntoView = function scrollIntoView() {};
if (!window.matchMedia) {
  window.matchMedia = (q: string) => ({ matches: false, media: q, onchange: null, addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false }) as MediaQueryList;
}

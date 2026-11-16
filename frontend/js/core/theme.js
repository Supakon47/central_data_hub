import { $ } from "./dom.js";

const THEME_STORAGE_KEY = "central-data-hub-theme";

function applyTheme(theme) {
  const isDark = theme === "dark";
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
  const button = $("#theme-toggle");
  button.querySelector("[aria-hidden]").textContent = isDark ? "☀" : "☾";
  button.querySelector(".theme-toggle-label").textContent = isDark
    ? "โหมดสว่าง"
    : "โหมดมืด";
  const label = isDark ? "เปิดโหมดสว่าง" : "เปิดโหมดมืด";
  button.setAttribute("aria-label", label);
  button.title = label;
}

export function initialiseTheme() {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  const preferredTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
  applyTheme(savedTheme || preferredTheme);
  $("#theme-toggle").addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
    applyTheme(nextTheme);
  });
}

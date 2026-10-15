const menu = document.querySelector(".menu-toggle");
menu.addEventListener("click", () => {
  const open = document.querySelector(".site-header").classList.toggle("open");
  menu.setAttribute("aria-expanded", String(open));
});

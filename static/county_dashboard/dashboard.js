(() => {
  const toggle = document.querySelector('[data-menu-toggle]');
  const sidebar = document.getElementById('sidebar');
  if (toggle && sidebar) toggle.addEventListener('click', () => sidebar.classList.toggle('sidebar-open'));

  document.querySelectorAll('[data-dismiss]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.getAttribute('data-confirm') || 'Continue?')) event.preventDefault();
    });
  });

  const imageInput = document.querySelector('[data-image-input]');
  const preview = document.querySelector('[data-upload-preview]');
  if (imageInput && preview) {
    imageInput.addEventListener('change', () => {
      preview.replaceChildren();
      const file = imageInput.files && imageInput.files[0];
      if (!file) {
        preview.innerHTML = '<span>▧</span><p>Image preview appears here</p>';
        return;
      }
      if (!file.type.startsWith('image/')) {
        preview.innerHTML = '<span>!</span><p>Please choose an image file.</p>';
        return;
      }
      const image = document.createElement('img');
      image.alt = 'Selected gallery image preview';
      image.src = URL.createObjectURL(file);
      image.onload = () => URL.revokeObjectURL(image.src);
      preview.appendChild(image);
    });
  }
})();

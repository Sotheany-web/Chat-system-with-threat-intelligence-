// smart-dropdown.js
class SmartDropdown {
  constructor(config = {}) {
    this.selector   = config.selector || '.dropdown-btn';
    this.gap        = config.gap || 6;
    this.edge       = config.edge || 8;
    this.defaultDir = config.defaultDir || 'bottom,top,right,left';

    this.openBtn  = null;
    this.openMenu = null;

    this.init();
  }

  init() {
    document.querySelectorAll(this.selector).forEach(btn => {
      const menu = btn.parentElement.querySelector('.dropdown-menu');
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const reopen = (this.openMenu === menu);
        this.close();
        if (!reopen) this.open(btn, menu);
      });
    });

    document.addEventListener('click', () => this.close());
    window.addEventListener('scroll', () => this.update(), { passive: true });
    window.addEventListener('resize', () => this.update());
  }

  open(btn, menu) {
    this.openBtn = btn;
    this.openMenu = menu;
    menu.classList.add('show');
    this.update();
    menu.style.visibility = 'visible';
  }

  close() {
    if (this.openMenu) {
      this.openMenu.classList.remove('show');
      this.openMenu.style.visibility = 'hidden';
    }
    this.openBtn = this.openMenu = null;
  }

  update() {
    if (!this.openMenu) return;

    const b = this.openBtn.getBoundingClientRect();
    const m = this.openMenu.getBoundingClientRect();
    const vw = innerWidth;
    const vh = innerHeight;

    const raw = this.openBtn.dataset.dir || this.defaultDir;
    let dirs = raw.split(/[\s,]+/).map(d => d.toLowerCase());
    if (!dirs.length) dirs = ['bottom', 'top', 'right', 'left'];

    let top, left;
    for (const d of dirs) {
      if (d === 'bottom' && b.bottom + this.gap + m.height <= vh - this.edge) {
        top = b.bottom + this.gap;
        left = this.clampX(b.left, m.width, vw);
        break;
      }
      if (d === 'top' && b.top - this.gap - m.height >= this.edge) {
        top = b.top - this.gap - m.height;
        left = this.clampX(b.left, m.width, vw);
        break;
      }
      if (d === 'right' && b.right + this.gap + m.width <= vw - this.edge) {
        top = this.clampY(b.top, m.height, vh);
        left = b.right + this.gap;
        break;
      }
      if (d === 'left' && b.left - this.gap - m.width >= this.edge) {
        top = this.clampY(b.top, m.height, vh);
        left = b.left - this.gap - m.width;
        break;
      }
    }

    if (top === undefined) top = Math.max((vh - m.height) / 2, this.edge);
    if (left === undefined) left = Math.max((vw - m.width) / 2, this.edge);

    this.openMenu.style.top = `${top}px`;
    this.openMenu.style.left = `${left}px`;
  }

  clampX(x, w, vw) {
    return Math.min(Math.max(x, this.edge), Math.max(vw - w - this.edge, this.edge));
  }

  clampY(y, h, vh) {
    return Math.min(Math.max(y, this.edge), Math.max(vh - h - this.edge, this.edge));
  }
}

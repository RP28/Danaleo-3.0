export const theme = {
  colors: {
    bg: '#080b12',
    panel: '#10131c',
    panelSoft: '#151a27',
    panelRaised: '#1a2030',
    border: '#273044',
    borderSoft: '#1f2636',
    text: '#e8edf8',
    muted: '#8f9bb3',
    faint: '#657089',
    primary: '#7c6cff',
    primarySoft: '#2d285f',
    accent: '#33d6c5',
    danger: '#ff647c',
    warning: '#ffc857',
    success: '#60d394',
    canvas: '#0c1018',
    white: '#f6f7fb'
  },
  radius: {
    sm: '10px',
    md: '16px',
    lg: '24px'
  },
  shadow: '0 24px 80px rgba(0, 0, 0, 0.32)'
};

export function injectThemeVars() {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(theme.colors)) {
    root.style.setProperty(`--${key}`, value);
  }
  for (const [key, value] of Object.entries(theme.radius)) {
    root.style.setProperty(`--radius-${key}`, value);
  }
  root.style.setProperty('--shadow', theme.shadow);
}

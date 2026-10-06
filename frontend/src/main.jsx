import { Component } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/figtree";
import "./style.css";

// Filet de sécurité : si un écran plante, on propose de recharger au lieu de laisser une page blanche.
class Guard extends Component {
  state = { broken: false };
  static getDerivedStateFromError() { return { broken: true }; }
  componentDidCatch(error) { console.error(error); }
  render() {
    if (!this.state.broken) return this.props.children;
    return (<div className="loading"><div>
      <h2>Un problème est survenu</h2>
      <p className="mute">Tes données ne sont pas touchées. Recharge la page pour continuer.</p>
      <button className="btn" onClick={() => { window.location.hash = ""; window.location.reload(); }}>Recharger</button>
    </div></div>);
  }
}

createRoot(document.getElementById("root")).render(<Guard><App /></Guard>);

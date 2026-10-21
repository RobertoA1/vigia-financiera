import { Component, type ReactNode } from 'react';
import { Brand, Notice } from './ui';
export class ErrorBoundary extends Component<{children: ReactNode}, {failed: boolean}> {
  state = {failed: false};
  static getDerivedStateFromError() {return {failed: true};}
  render() {
    if (this.state.failed) return <main className="boot"><Brand/><div className="panel-padded"><Notice kind="warning">No se pudo mostrar esta vista. Recarga para restablecer tu sesión y vuelve a intentarlo.</Notice><button className="button primary" onClick={() => window.location.reload()}>Recargar aplicación</button></div></main>;
    return this.props.children;
  }
}

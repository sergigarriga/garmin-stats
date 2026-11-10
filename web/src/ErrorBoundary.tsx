import { Component, type ErrorInfo, type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

type Props = {
  children: ReactNode;
  /** true: ocupa toda la pantalla (última red, alrededor de la app entera). Sin ello, solo el hueco de la página. */
  full?: boolean;
};

/** Si una pantalla falla al pintarse (un dato con una forma inesperada), el resto de la app sigue en pie:
 *  en vez de una página en blanco sale un aviso con botones para reintentar o volver al inicio. */
export default class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Pantalla con error:', error, info.componentStack);
  }

  componentDidMount() {
    window.addEventListener('hashchange', this.reset);
  }

  componentWillUnmount() {
    window.removeEventListener('hashchange', this.reset);
  }

  // Al cambiar de sección se vuelve a intentar: el fallo de una pantalla no se queda pegado en las demás.
  reset = () => { if (this.state.failed) this.setState({ failed: false }); };

  home = () => {
    if (window.location.hash === '#hoy' || window.location.hash === '') window.location.reload();
    else window.location.hash = '#hoy';
  };

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Box role="alert" sx={{ display: 'grid', placeItems: 'center', textAlign: 'center', p: 3, minHeight: this.props.full ? '100vh' : 320 }}>
        <Stack spacing={2} sx={{ alignItems: 'center', maxWidth: 420 }}>
          <Typography variant="h6">Esta pantalla no se ha podido mostrar</Typography>
          <Typography color="text.secondary">
            Algo ha fallado al enseñar esta parte. Tus datos están bien: prueba otra vez o vuelve al inicio.
          </Typography>
          <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', justifyContent: 'center' }}>
            <Button variant="contained" disableElevation onClick={this.reset} sx={{ borderRadius: 999 }}>Volver a intentar</Button>
            <Button variant="outlined" onClick={this.home} sx={{ borderRadius: 999 }}>Ir al inicio</Button>
          </Stack>
        </Stack>
      </Box>
    );
  }
}

// Apertura del chat en el móvil: el panel nace del botón del chat y crece hasta su sitio (y vuelve a él al cerrar).
// Se usa como transición del Drawer. Con «reducir movimiento» activado solo aparece y desaparece.
import { cloneElement, forwardRef, useRef, type ReactElement, type Ref } from 'react';
import { Transition } from 'react-transition-group';
import { useForkRef } from '@mui/material/utils';

const ENTER = 440, EXIT = 260;
const SPRING = 'cubic-bezier(.22, 1.06, .36, 1)';   // llega con un pelín de rebote
const BACK = 'cubic-bezier(.4, 0, .7, .2)';

interface Props {
  in?: boolean; appear?: boolean; children: ReactElement<{ style?: React.CSSProperties; ref?: Ref<unknown> }>;
  onEnter?: (node: HTMLElement, isAppearing: boolean) => void; onEntered?: (node: HTMLElement, isAppearing: boolean) => void;
  onExit?: (node: HTMLElement) => void; onExited?: (node: HTMLElement) => void;
}

const calm = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Centro del botón del chat que se ve, en coordenadas del panel (para que crezca desde ahí). */
function origin(node: HTMLElement): string {
  const btn = [...document.querySelectorAll<HTMLElement>('[data-chat-btn]')].find((b) => b.offsetParent !== null);
  const p = node.getBoundingClientRect();
  if (!btn) return `${p.width - 48}px ${p.height - 48}px`;
  const b = btn.getBoundingClientRect();
  return `${b.left + b.width / 2 - p.left}px ${b.top + b.height / 2 - p.top}px`;
}

const small = 'scale(0.06)';

export const ChatGrow = forwardRef<unknown, Props>(function ChatGrow(props, ref) {
  const { in: show, appear = true, children, onEnter, onEntered, onExit, onExited } = props;
  const nodeRef = useRef<HTMLElement>(null);
  const handleRef = useForkRef(nodeRef, ref, (children as unknown as { ref?: Ref<unknown> }).ref ?? children.props.ref);

  return (
    <Transition nodeRef={nodeRef} in={show} appear={appear} timeout={{ enter: ENTER, exit: EXIT }}
      onEnter={(appearing: boolean) => {
        const n = nodeRef.current; if (!n) return;
        n.style.transition = 'none';
        n.style.transform = 'none';
        n.style.transformOrigin = origin(n);
        n.style.opacity = '0';
        n.style.transform = calm() ? 'none' : small;
        n.style.willChange = 'transform, opacity';
        void n.offsetHeight;  // que el navegador tome el punto de partida antes de animar
        onEnter?.(n, appearing);
      }}
      onEntering={() => {
        const n = nodeRef.current; if (!n) return;
        n.style.transition = `transform ${ENTER}ms ${SPRING}, opacity 160ms ease-out`;
        n.style.transform = 'none';
        n.style.opacity = '1';
      }}
      onEntered={(appearing: boolean) => {
        const n = nodeRef.current; if (!n) return;
        // Sin transform al acabar: un transform puesto descoloca los elementos fijos y el teclado de iOS.
        n.style.transition = ''; n.style.transform = ''; n.style.willChange = '';
        onEntered?.(n, appearing);
      }}
      onExit={() => {
        const n = nodeRef.current; if (!n) return;
        n.style.transformOrigin = origin(n);
        n.style.willChange = 'transform, opacity';
        void n.offsetHeight;
        n.style.transition = `transform ${EXIT}ms ${BACK}, opacity ${EXIT - 60}ms ease-in 60ms`;
        n.style.transform = calm() ? 'none' : small;
        n.style.opacity = '0';
        onExit?.(n);
      }}
      onExited={() => { const n = nodeRef.current; if (n) onExited?.(n); }}>
      {(state: string) => cloneElement(children, {
        ref: handleRef,
        style: { visibility: state === 'exited' && !show ? 'hidden' : undefined, ...children.props.style },
      })}
    </Transition>
  );
});

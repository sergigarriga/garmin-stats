import { createContext, useContext } from 'react';

// true solo para la dueña de la cuenta: los costes de IA (€/$, topes, gasto) no se muestran a las invitadas.
export const OwnerCtx = createContext(false);
export const useIsOwner = () => useContext(OwnerCtx);

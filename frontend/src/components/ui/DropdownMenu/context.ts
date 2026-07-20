import { createContext } from 'react';

/** Lets `DropdownMenuItem` close the menu after it is activated. */
export const DropdownMenuContext = createContext<{ close: () => void }>({
  close: () => {},
});

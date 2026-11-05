import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import Button from './Button.jsx';

describe('Button component', () => {
  it('renderiza correctamente el contenido y la clase base por defecto', () => {
    render(<Button>Registrar venta</Button>);
    const button = screen.getByRole('button', { name: /registrar venta/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass('button', 'button--primary');
    expect(button).toHaveAttribute('type', 'button');
  });

  it('permite variantes visuales y clases personalizadas', () => {
    render(
      <Button variant="danger" className="custom-action">
        Eliminar
      </Button>
    );
    const button = screen.getByRole('button', { name: /eliminar/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass('button', 'button--danger', 'custom-action');
  });

  it('dispara el evento onClick cuando el usuario interactúa', async () => {
    const handleClick = vi.fn();
    const user = userEvent.setup();

    render(<Button onClick={handleClick}>Confirmar acción</Button>);
    const button = screen.getByRole('button', { name: /confirmar acción/i });

    await user.click(button);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('no ejecuta el evento si se encuentra deshabilitado', async () => {
    const handleClick = vi.fn();
    const user = userEvent.setup();

    render(
      <Button onClick={handleClick} disabled>
        Guardar cambios
      </Button>
    );
    const button = screen.getByRole('button', { name: /guardar cambios/i });
    expect(button).toBeDisabled();

    await user.click(button);
    expect(handleClick).not.toHaveBeenCalled();
  });
});

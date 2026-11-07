import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import PublicHomePage, { calculateLechonaEstimate } from './PublicHomePage.jsx';

describe('PublicHomePage - WhatsApp and Map integration', () => {
  it('calculadora conserva su lógica de estimación intacta', () => {
    expect(calculateLechonaEstimate(5)).toBe(60000);
    expect(calculateLechonaEstimate(25)).toBe(320000);
    expect(calculateLechonaEstimate(50)).toBe(520000);
    expect(calculateLechonaEstimate(100)).toBe(520000 + 50 * 8000);
  });

  it('todos los botones de WhatsApp conectan con el número y mensaje oficial', () => {
    render(<PublicHomePage />);

    const whatsappLinks = screen.getAllByRole('link', { name: /whatsapp|escríbenos/i });
    expect(whatsappLinks.length).toBe(5);

    const expectedNumber = '573142661472';
    const expectedMessageEncoded = encodeURIComponent(
      'Hola, estoy interesado en sus productos. ¿Me pueden brindar información?'
    );
    const expectedPrefix = `https://wa.me/${expectedNumber}?text=${expectedMessageEncoded}`;

    whatsappLinks.forEach((link) => {
      expect(link).toHaveAttribute('href', expectedPrefix);
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    // Validar presencia en las 5 ubicaciones clave
    expect(screen.getByRole('link', { name: /whatsapp domicilios/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /hacer pedido por whatsapp/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /pedir lechona por whatsapp/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /pedir hayacas por whatsapp/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /escríbenos/i })).toBeInTheDocument();
  });

  it('renderiza el mapa interactivo de OpenStreetMap centrado en Acacías, Meta con atribución', () => {
    render(<PublicHomePage />);

    const mapElement = screen.getByRole('application', { name: /acacías/i });
    expect(mapElement).toBeInTheDocument();

    const badge = screen.getByText(/despachos en acacías, meta y zonas aledañas/i);
    expect(badge).toBeInTheDocument();

    const osmAttribution = screen.getByRole('link', { name: /openstreetmap/i });
    expect(osmAttribution).toBeInTheDocument();
    expect(osmAttribution).toHaveAttribute('href', 'https://www.openstreetmap.org/copyright');
  });
});

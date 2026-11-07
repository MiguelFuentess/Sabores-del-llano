import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Centro geográfico de la zona urbana de Acacías, Meta, Colombia
const ACACIAS_URBAN_CENTER = [3.986, -73.758];
const DEFAULT_ZOOM = 14;

export default function AcaciasMap() {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);

  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    // Inicializar mapa de OpenStreetMap
    const map = L.map(mapContainerRef.current, {
      center: ACACIAS_URBAN_CENTER,
      zoom: DEFAULT_ZOOM,
      minZoom: 12,
      maxZoom: 18,
      scrollWheelZoom: true,
      zoomControl: true,
    });

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
    }).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  return (
    <div
      ref={mapContainerRef}
      className="public-coverage-map__canvas"
      aria-label="Mapa interactivo de OpenStreetMap centrado en la zona urbana de Acacías, Meta"
      role="application"
    />
  );
}

import { useOutletContext } from 'react-router-dom';
import Button from '../../../components/ui/Button.jsx';
import PageHeader from '../../../components/ui/PageHeader.jsx';

function SparklesIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 14.3 9.7 21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3L12 3ZM19 2v4m-2-2h4M5 17v4m-2-2h4" /></svg>;
}

function BulbIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.7 17h4.6M12 3v1m6.4 1.6-.7.7M21 12h-1M4 12H3m3.3-5.7-.7-.7m2.8 9.9a5 5 0 1 1 7.1 0l-.5.5a3.4 3.4 0 0 0-1 2.4v.5a2 2 0 1 1-4 0v-.5a3.4 3.4 0 0 0-1-2.4l-.5-.5Z" /></svg>;
}

function DownloadIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0 4.5-4.5M12 15l-4.5-4.5M4 16.5v2.25A2.25 2.25 0 0 0 6.25 21h11.5A2.25 2.25 0 0 0 20 18.75V16.5" /></svg>;
}

export default function DemandPage() {
  const { openMenu } = useOutletContext();

  return <div className="demand-page">
    <button className="orders-mobile-menu demand-mobile-menu" type="button" aria-label="Abrir menú" onClick={openMenu}><span /><span /><span /></button>
    <PageHeader title="Predicción de demanda" description="Estima la demanda futura para apoyar la planificación de la producción." />

    <section className="demand-card demand-config" aria-labelledby="demand-config-title">
      <div className="demand-card__intro">
        <h2 id="demand-config-title">Configurar estimación</h2>
        <p>Selecciona los datos y el período que deseas estimar.</p>
      </div>
      <hr />
      <div className="demand-fields">
        <label className="demand-field">
          <span>1. Producto</span>
          <select defaultValue="Hayacas" aria-label="Producto">
            <option>Hayacas</option>
            <option>Lechona</option>
          </select>
        </label>
        <label className="demand-field">
          <span>2. Período histórico</span>
          <select defaultValue="Últimos 3 meses" aria-label="Período histórico">
            <option>Últimos 3 meses</option>
            <option>Últimos 6 meses</option>
            <option>Último año</option>
          </select>
          <small>Define qué registros históricos se tendrán en cuenta.</small>
        </label>
        <label className="demand-field">
          <span>3. Horizonte de estimación</span>
          <select defaultValue="Próxima semana" aria-label="Horizonte de estimación">
            <option>Próxima semana</option>
            <option>Próximo mes</option>
            <option>Próximo trimestre</option>
          </select>
        </label>
      </div>
      <div className="demand-config__action">
        <Button><SparklesIcon />Generar estimación</Button>
      </div>
    </section>

    <section className="demand-card demand-result" aria-labelledby="demand-result-title">
      <div className="demand-result__heading">
        <h2 id="demand-result-title">Resultado de la estimación</h2>
        <div className="demand-result__actions">
          <Button variant="quiet" className="demand-report-button" aria-disabled="true" title="Exportación disponible en una etapa posterior"><DownloadIcon />Descargar reporte</Button>
          <span className="demand-demo-badge"><i />Vista demostrativa</span>
        </div>
      </div>
      <hr />
      <div className="demand-result__value">
        <p>Ejemplo visual · Hayacas · Próxima semana</p>
        <strong>180 unidades</strong>
        <span>Valor estático de muestra; no corresponde a un cálculo.</span>
      </div>
      <div className="demand-plan-wrap">
        <table className="demand-plan-table">
          <thead><tr><th scope="col">Día</th><th scope="col">Producto</th><th scope="col">Demanda estimada</th><th scope="col">Sobrantes disponibles</th><th scope="col">Producción sugerida</th></tr></thead>
          <tbody><tr><td colSpan="5">La planificación semanal estará disponible cuando se habilite la generación de estimaciones.</td></tr></tbody>
        </table>
      </div>
      <div className="demand-recommendation">
        <BulbIcon />
        <div><h3>Recomendaciones explicables sobre las cantidades propuestas</h3><p>Este espacio mostrará los motivos de las cantidades propuestas cuando se incorpore la lógica de estimación. Actualmente la vista es estática y no calcula demanda ni recomendaciones.</p></div>
      </div>
    </section>
  </div>;
}


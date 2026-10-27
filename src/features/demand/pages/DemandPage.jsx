import { useOutletContext } from 'react-router-dom';
import Button from '../../../components/ui/Button.jsx';
import PageHeader from '../../../components/ui/PageHeader.jsx';

function SparklesIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 14.3 9.7 21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3L12 3ZM19 2v4m-2-2h4M5 17v4m-2-2h4" /></svg>;
}

function BulbIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.7 17h4.6M12 3v1m6.4 1.6-.7.7M21 12h-1M4 12H3m3.3-5.7-.7-.7m2.8 9.9a5 5 0 1 1 7.1 0l-.5.5a3.4 3.4 0 0 0-1 2.4v.5a2 2 0 1 1-4 0v-.5a3.4 3.4 0 0 0-1-2.4l-.5-.5Z" /></svg>;
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
            <option>Tamales</option>
            <option>Empanadas</option>
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
        <span className="demand-demo-badge"><i />Vista demostrativa</span>
      </div>
      <hr />
      <div className="demand-result__value">
        <p>Ejemplo visual · Hayacas · Próxima semana</p>
        <strong>180 unidades</strong>
        <span>Valor estático de muestra; no corresponde a un cálculo.</span>
      </div>
      <div className="demand-recommendation">
        <BulbIcon />
        <div><h3>Recomendación para la producción</h3><p>Utiliza esta cantidad como referencia visual. La vista aún no genera estimaciones ni recomendaciones reales.</p></div>
      </div>
    </section>
  </div>;
}


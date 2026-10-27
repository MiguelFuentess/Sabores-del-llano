import PageHeader from './PageHeader.jsx';

export default function PlaceholderPage({ title, description }) {
  return <>
    <PageHeader title={title} description={description} />
    <section className="placeholder-card" aria-label="Área de contenido">
      <span className="placeholder-card__ornament" aria-hidden="true">✦</span>
      <p>La interfaz de esta sección se desarrollará en la siguiente fase.</p>
    </section>
  </>;
}

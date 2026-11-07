import { useState } from 'react';
import AcaciasMap from '../components/AcaciasMap.jsx';
import '../public.css';

const WHATSAPP_PHONE = '573142661472';
const WHATSAPP_MESSAGE = 'Hola, estoy interesado en sus productos. ¿Me pueden brindar información?';
const WHATSAPP_URL = `https://wa.me/${WHATSAPP_PHONE}?text=${encodeURIComponent(WHATSAPP_MESSAGE)}`;

export function calculateLechonaEstimate(personCount) {
  const requestedCount = Number(personCount);
  const people = Number.isFinite(requestedCount) ? Math.min(150, Math.max(5, Math.round(requestedCount))) : 5;
  let price;

  if (people <= 25) price = 60000 + ((people - 5) / 20) * (320000 - 60000);
  else if (people <= 50) price = 320000 + ((people - 25) / 25) * (520000 - 320000);
  else price = 520000 + (people - 50) * 8000;

  return Math.max(0, Math.round(price));
}

const formatCOP = (value) => `$${new Intl.NumberFormat('es-CO').format(value)} COP`;

const assets = {
  emblem: 'https://lh3.googleusercontent.com/aida-public/AB6AXuAVp0wQ9txKLXiOp8QmX-Yequc5L647xMa_4uyIbTLFEw54IahINA5IXhNj4prgSwd-VuaPaW22DT_zPG1FjSMy7o_LCn8UNeTuq5d4HmPqU_iNNDJZ7J4sfaGegfJ9BvHistIIRB_IXpLExr8r_MD-AxB0HJbxGlE49J2JzKybp_taXPpiXjDZrF58wkppiQfD9U4gDYFg1h3bFamJUSYeZaVeBQ5o9fJggpmEwJj7CHVJGY1oecHR',
  hero: 'https://lh3.googleusercontent.com/aida-public/AB6AXuALJSuV-syUuNvHiYjzdJZn3B-qySu4PJHFghYzmEghd3kxa4vzOoq3SdHCcPfJHoxlHOIkyQm6mSZKSsdn0ThucP9Vqs6XQ_aj5PJXdysxIIQnSaS-RKS85dxmhfN41B0oJwNaLv9-dweAf2-zncmgN5sOKHjxj7-Gq6TMxeWhiFoVRRmMltCORrWPdrflQIACwKqss2Fm3yfJXzRCqd_sslSLVwZwT0Za0V4jgYaUXxJzanKOOtxy',
  lechona: 'https://static.wixstatic.com/media/a7501f_31dbd16b1ca14a3a8144b42f93c77715~mv2.jpg/v1/fill/w_550,h_389,al_c,q_80,enc_avif,quality_auto/a7501f_31dbd16b1ca14a3a8144b42f93c77715~mv2.jpg',
  hayacas: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDZm58gnReNPK6QEHAYfJD5AlfzZF9OznFy74N7Ce-BykRKOxNEsxuYLoqrJ7kZuNvRImuqs4Xhr279bRpzEu1HqM8wtjBajbolK2fLT12IZoym3IKmHgNJI4lDdfa92rG1gKY7Dkowe7dBQ1olKkz5BFHv_AZLyd9KKjQC63OIQI2rqFN_q33DranprNT1QV1HBm1nm6RiJ_Qs5Y-t9cQ0uL0JhMqQNeiGtX-FiD05Zy8Y_1i-vYld',
};

function Icon({ children, className = '' }) {
  return <span className={`public-icon ${className}`.trim()} aria-hidden="true">{children}</span>;
}

function ContactDisplay({ children, className = '' }) {
  return (
    <a
      href={WHATSAPP_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={`public-contact-display ${className}`.trim()}
    >
      {children}
    </a>
  );
}

const craftSteps = [
  { number: '01', icon: 'soup_kitchen', title: 'Adobo Criollo de 24h', text: 'Marinamos las carnes selectas con ajos machacados, comino y cebolla larga recién cosechada para un sabor penetrante.', tone: 'red' },
  { number: '02', icon: 'spa', title: 'Envoltura Manual', text: 'Ahumamos ligeramente las hojas de plátano para darles flexibilidad y amarramos a mano con fique natural, conservando todos los jugos.', tone: 'green' },
  { number: '03', icon: 'local_fire_department', title: 'Madrugada de Horno', text: 'La lechona entra al horno a las 8:00 PM y se cocina a fuego pausado durante 12 horas hasta alcanzar el crujido dorado.', tone: 'red' },
  { number: '04', icon: 'dinner_dining', title: 'Caliente en su Mesa', text: 'Despachos dominicales a primera hora en empaque térmico que conserva el calor de fogón hasta el momento de servir.', tone: 'brown' },
];

function ProductCard({ kind, image, imageAlt, badge, rating, title, description, options }) {
  return (
    <article className="public-product-card">
      <div className="public-product-card__image">
        <img src={image} alt={imageAlt} loading="lazy" />
        <span className="public-product-card__badge">{badge}</span>
        <span className="public-product-card__rating"><Icon>{kind === 'lechona' ? 'star' : 'favorite'}</Icon>{rating}</span>
      </div>
      <div className="public-product-card__content">
        <div className="public-product-card__details">
          <h3>{title}</h3>
          <p className="public-product-card__description">{description}</p>
        </div>
        <div className="public-product-options-panel">
          <div className="public-options-label">Opciones Disponibles:</div>
          <ul className="public-product-options">
            {options.map((option) => (
              <li key={option.name}>
                <div><strong>{option.name}</strong><small>{option.detail}</small></div>
                {option.price ? <b>{option.price}</b> : <span className="public-quote">Cotizar</span>}
              </li>
            ))}
          </ul>
        </div>
        <ContactDisplay className="public-product-card__contact"><Icon>shopping_cart</Icon>Pedir {kind === 'lechona' ? 'Lechona' : 'Hayacas'} por WhatsApp</ContactDisplay>
      </div>
    </article>
  );
}

export default function PublicHomePage() {
  const [people, setPeople] = useState(25);
  const estimatedPrice = calculateLechonaEstimate(people);
  const sliderProgress = `${((people - 5) / (150 - 5)) * 100}%`;
  const recommendation = people < 25
    ? { title: 'Porciones individuales de lechona', detail: `${people} personas · referencia de $12.000 COP por plato` }
    : people < 50
      ? { title: 'Cojín Familiar', detail: `${people} personas · estimación basada en la referencia del cojín para 25 personas` }
      : { title: 'Presentación para grupos grandes', detail: `${people} personas · precio estimado matemáticamente, pendiente de confirmación comercial` };

  return (
    <main className="public-site" id="inicio">
      <header className="public-header">
        <a className="public-brand" href="#inicio" aria-label="Sabores del Llano, inicio">
          <img src={assets.emblem} alt="" />
          <span><strong>Sabores del llano</strong><small>TRADICION CULINARIA</small></span>
        </a>
        <nav className="public-nav" aria-label="Navegación principal">
          <a className="public-nav__active" href="#inicio">Inicio</a>
          <a href="#menu">Especialidades</a>
          <a href="#tradicion">Tradición Familiar</a>
          <a href="#pedidos">Contacto y Pedidos</a>
        </nav>
        <ContactDisplay className="public-header__contact"><Icon>chat</Icon>WhatsApp Domicilios</ContactDisplay>
      </header>

      <section className="public-hero">
        <div className="public-hero__intro">
          <span className="public-hero__eyebrow"><Icon>eco</Icon>Herencia Viva</span>
          <h1>Tradición &amp; <em>Herencia Familiar</em></h1>
          <p>Preparación devota en horno de leña, hojas campesinas de plátano y el crujido dorado<br className="public-desktop-break" /> inconfundible de nuestra tierra.</p>
        </div>
        <figure className="public-hero__image">
          <img src={assets.hero} alt="Banquete tradicional colombiano de lechona y hayacas" fetchPriority="high" />
          <figcaption className="public-hero__image-labels">
            <span>100% Artesanal Tolimense</span>
            <span><Icon>check_circle</Icon>Garantía de Crocancia</span>
          </figcaption>
        </figure>
        <ContactDisplay className="public-hero__contact"><Icon>chat</Icon>Hacer Pedido por WhatsApp</ContactDisplay>
        <div className="public-qualities">
          <div><span className="public-quality-icon public-quality-icon--red"><Icon>verified</Icon></span><span><b>100% Cerdo Seleccionado</b><small>Carne magra, marinada en adobo natural</small></span></div>
          <div><span className="public-quality-icon public-quality-icon--gold"><Icon>local_fire_department</Icon></span><span><b>12 Horas de Horno a Leña</b><small>Cocción serena, cuero extra crocante</small></span></div>
          <div><span className="public-quality-icon public-quality-icon--green"><Icon>spa</Icon></span><span><b>Hojas Frescas de Bijao</b><small>Traídas directamente del campo tolimense</small></span></div>
        </div>
      </section>

      <section className="public-specialties" id="menu">
        <div className="public-section-heading">
          <span>Enfoque Puro &amp; Calidad Inquebrantable</span>
          <h2>Nuestras Únicas Dos Especialidades</h2>
          <p>No hacemos todo, pero perfeccionamos lo esencial. Dos recetas emblemáticas preparadas<br className="public-desktop-break" /> con la paciencia y el cariño de un domingo familiar.</p>
        </div>
        <div className="public-product-grid">
          <ProductCard
            kind="lechona"
            image={assets.lechona}
            imageAlt="Auténtica Lechona Tolimense tradicional servida con cuero crocante"
            badge="Receta Insigne"
            rating="4.9 / 5.0 (380+ reseñas)"
            title="Lechona Tolimense Tradicional"
            description="Cuero crocante dorado a la perfección con fuego vivo, carne de cerdo desmechada tierna con arveja amarilla criolla, marinada en adobo secreto campesino."
            options={[
              { name: 'Porción Personal Generosa', detail: '450g aprox. + Cuero crocante + Arepa', price: '$12.000 COP' },
              { name: 'Cojín Familiar (25 Personas)', detail: 'Incluye insulsas, platos y ají artesanal', price: '$320.000 COP' },
              { name: 'Lechona Entera para Eventos', detail: '50 hasta 120 porciones con despresado en sitio' },
            ]}
          />
          <ProductCard
            kind="hayacas"
            image={assets.hayacas}
            imageAlt="Hayacas tradicionales tolimenses envueltas en hojas de bijao"
            badge="Herencia de Bijao"
            rating="Favorito de Domingo"
            title="Hayacas Artesanales"
            description="Masa suave de arroz llanero cocinada en caldo de carnes, rellena con trozos selectos de pierna de cerdo, pollo de campo, zanahoria y guiso criollo. Envueltas amorosamente en hoja de plátano."
            options={[
              { name: 'Unidad Individual', detail: '500g generosa envuelta en bijao', price: '$10.000 COP' },
              { name: 'Combo Desayuno Dominical (x4)', detail: '4 Hayacas + chocolate tolimense de pastilla', price: '$52.000 COP' },
              { name: 'Caja Regalo Familiar (x12)', detail: 'Empaque artesanal especial para compartir', price: '$150.000 COP' },
            ]}
          />
        </div>
      </section>

      <section className="public-tradition" id="tradicion">
        <div className="public-section-heading">
          <span>Paso a Paso Ancestral</span>
          <h2>El Ritual del Horno y la Hoja</h2>
          <p>Sin conservantes ni atajos industriales. Cada fin de semana repetimos con fervor la misma<br className="public-desktop-break" /> técnica aprendida en las cocinas de barro del Tolima Grande.</p>
        </div>
        <div className="public-craft-grid">
          {craftSteps.map((step) => (
            <article className="public-craft-card" key={step.number}>
              <strong className="public-craft-card__number">{step.number}</strong>
              <Icon className={`public-craft-card__icon public-craft-card__icon--${step.tone}`}>{step.icon}</Icon>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="public-planner" aria-label="Calculadora para eventos y familias">
        <div className="public-planner-card">
          <div className="public-planner__form">
            <span className="public-section-eyebrow">Planificador Inteligente</span>
            <h2>Calculadora para Eventos y Familias</h2>
            <p>¿Planeas un bautizo, cumpleaños dominical o reunión de empresa? Desliza para saber exactamente cuánto pedir.</p>
            <div className="public-planner__label"><b>Número de Comensales:</b><strong>{people}</strong></div>
            <div className="public-range">
              <span style={{ width: sliderProgress }} />
              <i style={{ left: sliderProgress }} />
              <input className="public-range__input" type="range" min="5" max="150" step="1" value={people} onChange={(event) => setPeople(Number(event.target.value))} aria-label="Número de comensales" />
            </div>
            <div className="public-range-marks"><span>5 Personas</span><span>50 Personas</span><span>100 Personas</span><span>150+ Personas</span></div>
            <div className="public-planner__presets">
              {[[10, 'Reunión Íntima (10)'], [25, 'Cojín Estándar (25)'], [50, 'Fiesta Grande (50)'], [100, 'Empresarial (100)']].map(([count, label]) => <button key={count} type="button" aria-pressed={people === count} onClick={() => setPeople(count)}>{label}</button>)}
            </div>
          </div>
          <aside className="public-recommendation">
            <h3>Recomendación Sugerida:</h3>
            <div className="public-recommendation__item"><Icon>restaurant</Icon><div><b>{recommendation.title}</b><small>{recommendation.detail}</small></div></div>
            <div className="public-recommendation__item public-recommendation__cost"><Icon>payments</Icon><div><b>Presupuesto Estimado:</b><strong>{formatCOP(estimatedPrice)}</strong></div></div>
          </aside>
        </div>
      </section>

      <section className="public-delivery" id="pedidos">
        <div className="public-section-heading">
          <span>Despachos &amp; Domicilios</span>
          <h2>¿Cómo Ordenar tu Pedido?</h2>
          <p>Horneamos por lotes artesanales para garantizar máxima frescura. Recomendamos reservar tus platos con anticipación para los fines de semana.</p>
        </div>
        <div className="public-delivery__options">
          <article><h3><Icon>calendar_today</Icon>Sabado, Domingo y Festivos</h3><p>Despacho regular de porciones personales y combos familiares desde las 7:30 AM hasta agotar existencias del día.</p></article>
          <article><h3><Icon>event_available</Icon>Eventos Todos los Días</h3><p>Cojines y pedidos masivos (desde 20 porciones) se despachan de Lunes a Domingo con reserva previa de 48 horas.</p></article>
        </div>
        <h3 className="public-delivery__map-title">Zona de Cobertura y Domicilios</h3>
        <div className="public-coverage-map">
          <AcaciasMap />
          <span className="public-coverage-map__badge">
            <Icon>pin_drop</Icon>Despachos en Acacías, Meta y zonas aledañas
          </span>
        </div>
      </section>

      <section className="public-final-cta">
        <span>El Auténtico Toque Campesino</span>
        <h2>¿Listo para saborear la verdadera lechona tolimense?</h2>
        <p>Atendemos pedidos corporativos, matrimonios, bautizos y reuniones familiares en todo el departamento.</p>
        <ContactDisplay><Icon>chat</Icon>Escríbenos</ContactDisplay>
      </section>

      <footer className="public-footer">
        <div className="public-footer__columns">
          <div className="public-footer__brand">
            <div><img src={assets.emblem} alt="" /><strong>Sabores del llano</strong></div>
            <p>Herencia gastronómica. Preparación artesanal de lechona y hayacas envueltas en hojas frescas de plátano con el auténtico sazón campesino.</p>
          </div>
          <div><h3>Atención y Despachos</h3><p>Sábados, Domingos y Festivos: 7:00 AM - 5:00 PM.</p><p>Encargos empresariales y eventos familiares durante toda la semana con 48h de anticipación.</p></div>
          <div><h3>Compromiso Artesanal</h3><p>Garantizamos cuero crocante, carnes selectas marinadas en adobo casero.</p></div>
        </div>
        <div className="public-footer__copyright">© 2026 Sabores del llano. Tradición Culinaria.</div>
      </footer>
    </main>
  );
}

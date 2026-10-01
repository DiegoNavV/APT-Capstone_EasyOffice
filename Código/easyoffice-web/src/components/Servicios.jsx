const SERVICIOS = [
  {
    id: 'domicilio-tributario',
    nombre: 'Domicilio tributario',
    descripcion:
      'Aloje su emprendimiento en un domicilio con funcionamiento experto y continuo por más de 15 años sin interrupciones. Cumpla todos los requisitos exigidos a su negocio, por el Servicio de Impuestos Internos y municipalidades. Cobertura total en regiones Metropolitana y de Valparaíso.',
    ctas: [{ label: 'Ver planes', href: '#' }],
    bg: 'bg-primary-light',
    disponibleEnMVP: true,
    tramiteHref: '/iniciar-tramite'
  },
  {
    id: 'contabilidad',
    nombre: 'Contabilidad & Tributaria',
    descripcion:
      'Diseñamos un servicio integral de asesoría contable, cumplimiento tributario y laboral para que empresas y socios declaren los impuestos e imposiciones de forma exacta y oportuna. Contrate nuestra experiencia técnica en impuestos para que alcance el equilibrio tributario en su patrimonio y comience a pagar lo correcto.',
    ctas: [{ label: 'Ver planes', href: '#' }],
    bg: 'bg-white',
    disponibleEnMVP: false
  },
  {
    id: 'firmas-electronicas',
    nombre: 'Firmas Electrónicas',
    descripcion:
      'Digitalice sus procesos de gestión documental y de firmas electrónicas en su negocio. Firme y autentifique documentos de uso frecuente, tales como: contratos de arriendo o de trabajo, poderes, autorizaciones, promesas de compra venta, declaraciones juradas y muchos más. Autentifique sus documentos con firma electrónica avanzada, Clave Única y nuestra red de notarios digitales.',
    ctas: [
      { label: 'Comprar firmas', href: '#' },
      { label: 'Necesito un plan', href: '#' }
    ],
    bg: 'bg-primary-light',
    disponibleEnMVP: true,
    tramiteHref: '/iniciar-tramite'
  },
  {
    id: 'empresa-en-1-dia',
    nombre: 'Empresa en 1 Día',
    descripcion:
      'Elija la forma de configurar su empresa. A través del registro de empresas y sociedades creamos su empresa en menos de 3 horas. Para más información sobre el tipo de sociedad y requisitos de cada una, solicite asesoría con un experto.',
    ctas: [
      { label: 'Crear empresa', href: '#' },
      { label: 'Quiero saber más', href: '#' }
    ],
    bg: 'bg-white',
    disponibleEnMVP: false
  },
  {
    id: 'rebaja-tributaria',
    nombre: 'Rebaja Tributaria',
    pregunta: '¿Por qué pagar el doble del valor por un impuesto?',
    descripcion:
      'Reduzca sus impuestos, incorporando nuestro servicio en su planificación tributaria y disminuya en 50% el pago del impuesto al capital propio, en su Declaración Anual de Renta. Aproveche el beneficio tributario otorgado por la Municipalidad de La Florida, región metropolitana. Deje su dinero en buenas manos y reduzca su tasa impositiva.',
    ctas: [{ label: 'Contratar rebaja tributaria', href: '#' }],
    bg: 'bg-primary-light',
    disponibleEnMVP: false
  }
]

function Boton({ label, href, primary = true }) {
  return (
    <a
      href={href}
      className={`inline-flex items-center gap-2 text-sm font-bold px-5 py-2.5 rounded-md transition-colors
        ${primary ? 'bg-primary hover:bg-primary-dark text-white' : 'border border-primary text-primary hover:bg-primary-light'}`}
    >
      {label.toUpperCase()} <span>→</span>
    </a>
  )
}

export default function Servicios({ onIniciarTramite }) {
  return (
    <div>
      {SERVICIOS.map((servicio, i) => (
        <section
          key={servicio.id}
          id={servicio.id}
          className={`${servicio.bg} py-16`}
        >
          <div
            className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-2 gap-12 items-center ${
              i % 2 === 1 ? 'lg:[&>*:first-child]:order-2' : ''
            }`}
          >
            {/* TODO: reemplazar por la foto real de cada servicio */}
            <div className="w-full aspect-[4/3] bg-gray-200 rounded-xl flex items-center justify-center text-gray-400 text-sm">
              Foto {servicio.nombre}
            </div>

            <div>
              <h3 className="text-primary text-2xl sm:text-3xl font-extrabold">{servicio.nombre}</h3>
              {servicio.pregunta && (
                <p className="mt-2 font-semibold text-ink">{servicio.pregunta}</p>
              )}
              <p className="mt-3 text-gray-700 leading-relaxed">{servicio.descripcion}</p>

              <div className="mt-6 flex flex-wrap gap-3">
                {servicio.ctas.map((cta) => (
                  <Boton key={cta.label} label={cta.label} href={cta.href} />
                ))}
                {servicio.disponibleEnMVP && (
                  <button type="button" onClick={onIniciarTramite}
                    className="inline-flex items-center gap-2 text-sm font-bold px-5 py-2.5 rounded-md border-2 border-primary text-primary hover:bg-primary hover:text-white transition-colors"
                  >
                    INICIAR TRÁMITE →
                  </button>
                )}
              </div>
            </div>
          </div>
        </section>
      ))}
    </div>
  )
}

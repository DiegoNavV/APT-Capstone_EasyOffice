const SERVICIOS_SELECT = [
  'Domicilio tributario',
  'Contabilidad',
  'Recursos humanos',
  'Creación de empresa',
  'Firma electrónica',
  'Casilla tributaria'
]

export default function Hero() {
  return (
    <section id="inicio" className="relative bg-ink text-white overflow-hidden">
      {/* TODO: reemplazar por la foto real de oficina del sitio (bg-cover) cuando tengamos el asset */}
      <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-ink to-gray-900" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold leading-tight">
            Hemos creado y activado más de 5.000 emprendimientos exitosos.
          </h1>
          <p className="mt-6 text-lg text-gray-300 max-w-lg">
            En easy office, llevamos más de 15 años ayudando a las personas a hacer más fácil y
            eficiente la manera de emprender. Conviértase, usted también, en un emprendedor
            exitoso e inicie actividad sin trabas ni tropiezos.
          </p>
          <a
            href="https://calendly.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-8 inline-block bg-primary hover:bg-primary-dark text-white font-semibold px-6 py-3 rounded-md transition-colors"
          >
            ¿Reunámonos 30 minutos?
          </a>
        </div>

        {/* Card CONTACTO */}
        <div className="bg-white text-ink rounded-xl p-6 sm:p-8 shadow-xl">
          <h2 className="text-primary text-2xl font-extrabold">CONTACTO</h2>

          <form className="mt-4 space-y-3">
            <Campo tipo="select">
              <label className="text-sm text-gray-500 block mb-1">Seleccione servicio</label>
              <select className="w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm">
                {SERVICIOS_SELECT.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Campo>

            <input
              type="text"
              placeholder="Nombre completo"
              className="w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm"
            />
            <input
              type="email"
              placeholder="Correo electrónico"
              className="w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm"
            />
            <input
              type="text"
              placeholder="Teléfono"
              className="w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm"
            />
            <textarea
              placeholder="Escriba su mensaje..."
              rows={3}
              className="w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm resize-none"
            />

            <button
              type="submit"
              className="w-full bg-primary hover:bg-primary-dark text-white font-semibold py-3 rounded-md transition-colors"
            >
              Enviar
            </button>
          </form>
        </div>
      </div>
    </section>
  )
}

function Campo({ children }) {
  return <div>{children}</div>
}

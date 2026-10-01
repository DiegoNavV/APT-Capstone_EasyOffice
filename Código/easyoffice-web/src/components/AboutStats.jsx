export default function AboutStats() {
  return (
    <section id="sobre-nosotros" className="py-16 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-2 gap-12 items-start">
        <div>
          {/* TODO: reemplazar por la foto real de la sección "Sobre nosotros" */}
          <div className="w-full aspect-[4/3] bg-gray-100 rounded-xl flex items-center justify-center text-gray-400 text-sm">
            Foto equipo / emprendedor
          </div>

          <div className="mt-8 flex gap-16 border-t border-gray-200 pt-6">
            <div>
              <p className="text-4xl font-extrabold text-ink">5000+</p>
              <p className="mt-1 text-sm text-gray-600">Emprendimientos exitosos</p>
            </div>
            <div>
              <p className="text-4xl font-extrabold text-ink">15+</p>
              <p className="mt-1 text-sm text-gray-600">Años de experiencia</p>
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-primary text-3xl font-extrabold">Sobre nosotros</h2>
          <p className="mt-4 text-gray-700 leading-relaxed">
            Easy Office es un centro de emprendimiento, red de oficinas equipadas y servicios
            digitales. Somos la plataforma que provee servicios para la creación, activación y
            operación de emprendimientos 100% digitales.
          </p>
          <p className="mt-4 text-gray-700 leading-relaxed">
            Proveemos soluciones de contabilidad y asesoría tributaria, creación de empresa,
            oficina de partes, domicilio tributario con direcciones verificadas, firmas
            electrónicas y servicios para todo el ciclo de vida de su empresa. Fomentamos la
            transparencia y el oportuno cumplimiento administrativo, tributario y laboral de
            todos nuestros asociados.
          </p>
          <p className="mt-4 text-gray-700 leading-relaxed">
            Nuestra misión es hacer más fácil y eficiente la experiencia de emprender.
          </p>
        </div>
      </div>
    </section>
  )
}

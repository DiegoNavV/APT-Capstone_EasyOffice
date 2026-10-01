const ENLACES = ['Inicio', 'Domicilio tributario', 'Contabilidad', 'Firmas Electrónicas', 'Asesoría Empresas', 'Rebaja Tributaria']

export default function Footer() {
  return (
    <footer className="bg-ink text-gray-300">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-14 grid sm:grid-cols-2 lg:grid-cols-4 gap-10">
        <div>
          <svg width="70" height="70" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="14" cy="20" r="9" stroke="#22B14C" strokeWidth="4" />
            <circle cx="26" cy="20" r="9" stroke="#22B14C" strokeWidth="4" />
          </svg>
          <p className="mt-2 font-bold text-white">easy office</p>
        </div>

        <div>
          <h4 className="font-semibold text-white mb-3">Enlaces útiles:</h4>
          <ul className="space-y-2 text-sm">
            {ENLACES.map((e, i) => (
              <li key={e} className={i === 0 ? 'text-primary font-medium' : ''}>{e}</li>
            ))}
          </ul>
        </div>

        <div>
          <h4 className="font-semibold text-white mb-3">Contáctanos:</h4>
          <ul className="space-y-2 text-sm">
            <li>Casa Matriz: ZIP 2362633 – Región de Valparaíso</li>
            <li>Sucursal: ZIP 8260183 – Región Metropolitana</li>
            <li>E-mail: info@easyoffice.cl</li>
            <li>Teléfono: +56 2 2277 7781</li>
            <li>Horario de lunes a jueves de 08:30 a 17:30 horas, viernes de 08:30 a 14:30 horas, excepto festivos.</li>
          </ul>
        </div>

        <div>
          <h4 className="font-semibold text-white mb-3">Síguenos:</h4>
          <p className="text-sm">
            Conéctate con nuestras redes sociales, conoce nuestros servicios y recibe toda la
            información que necesitas para contratar. Infórmese sobre las condiciones y
            características de cada servicio.
          </p>
          <div className="mt-4 flex gap-3">
            {['in', 'f', 'ig', 'x'].map((r) => (
              <span
                key={r}
                className="w-9 h-9 rounded-full border border-gray-500 flex items-center justify-center text-xs"
              >
                {r}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-primary text-ink text-center text-xs font-medium py-2">
        Diseño web por WEBNINJA LAB
      </div>
    </footer>
  )
}

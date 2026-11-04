import { Link } from 'react-router-dom'

// Secciones del inicio a las que llevan el menú del header (escritorio y celular) y los "Enlaces útiles" del footer.
export const NAV_LINKS = [
  { label: 'Inicio', id: 'inicio' },
  { label: 'Domicilio tributario', id: 'domicilio-tributario' },
  { label: 'Contabilidad', id: 'contabilidad' },
  { label: 'Firmas Electrónicas', id: 'firmas-electronicas' },
  { label: 'Asesoría Empresas', id: 'empresa-en-1-dia' },
  { label: 'Rebaja Tributaria', id: 'rebaja-tributaria' }
]

// Dentro del home se salta a la sección; desde otra página se vuelve al home y se baja a ella (ver Home.jsx).
export function EnlaceSeccion({ enlace, enHome, className, onClick }) {
  return enHome ? (
    <a href={`#${enlace.id}`} className={className} onClick={onClick}>
      {enlace.label}
    </a>
  ) : (
    <Link to={{ pathname: '/', hash: `#${enlace.id}` }} className={className} onClick={onClick}>
      {enlace.label}
    </Link>
  )
}

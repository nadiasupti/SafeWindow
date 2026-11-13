/** A screen's title with its icon and one short line under it. */
export default function PageHead({ Icon, title, sub, tone }) {
  return (
    <header className="page-head">
      {Icon && <span className={tone ? `page-icon ${tone}` : 'page-icon'} aria-hidden="true"><Icon size={24} /></span>}
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
    </header>
  )
}

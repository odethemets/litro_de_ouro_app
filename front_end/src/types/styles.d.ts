// Tipagem dos arquivos CSS Modules carregados pelo bundler.
declare module "*.module.css" {
  const classes: Readonly<Record<string, string>>;
  export default classes;
}

// Importação global utilizada pelo arquivo de tema.
declare module "@/global.css";

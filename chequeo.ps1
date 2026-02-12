.\inventario_ad_adonly_resumen.ps1 `
   -InputCsv .\equipos.csv `io_ad_resumen.csv
   -OutCsv .\inventario_ad.csv `d.csv con 126 filas.
   -OutSummaryCsv .\inventario_ad_resumen.csv `
   -SearchBaseDN "OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp" `
   -DomainSuffix "teva.corp" `
   -DomainController USNOWDC04.Teva.Corp `
   -Verbose

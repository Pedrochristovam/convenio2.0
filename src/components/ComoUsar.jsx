import React from 'react'
import { BookOpen } from 'lucide-react'

const SECOES = [
    ['visao', 'Visão geral'],
    ['pastas', 'Pastas de convênio'],
    ['volumes', 'Enviar volumes'],
    ['analise', 'Gerar a Análise Documental'],
    ['ler', 'Ler o resultado'],
    ['saidas', 'Documentos de saída'],
    ['extrato', 'Extrato financeiro'],
    ['sempasta', 'Arquivos sem pasta'],
    ['limites', 'Cuidados e limites'],
    ['faq', 'Perguntas frequentes'],
]

function Secao({ id, titulo, children }) {
    return (
        <section id={`ajuda-${id}`} className="scroll-mt-10 border-t border-slate-100 pt-10">
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900">{titulo}</h2>
            <div className="mt-4 space-y-4 text-[15px] leading-relaxed text-slate-600">{children}</div>
        </section>
    )
}

function Passos({ itens }) {
    return (
        <ol className="space-y-3">
            {itens.map(([t, d], i) => (
                <li key={t} className="flex gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white">{i + 1}</span>
                    <p><strong className="font-semibold text-slate-800">{t}</strong> {d}</p>
                </li>
            ))}
        </ol>
    )
}

function Dica({ children, tipo = 'dica' }) {
    const cor = tipo === 'atencao' ? 'border-amber-400 bg-amber-50/60 text-amber-900' : 'border-indigo-400 bg-indigo-50/50 text-indigo-950'
    return <p className={`border-l-4 px-4 py-3 text-sm ${cor}`}><strong>{tipo === 'atencao' ? 'Atenção: ' : 'Dica: '}</strong>{children}</p>
}

function Termos({ itens }) {
    return (
        <dl className="divide-y divide-slate-100">
            {itens.map(([t, d]) => (
                <div key={t} className="grid gap-1 py-3 md:grid-cols-[200px_1fr] md:gap-6">
                    <dt className="font-medium text-slate-800">{t}</dt>
                    <dd>{d}</dd>
                </div>
            ))}
        </dl>
    )
}

export default function ComoUsar() {
    const ir = (id) => document.getElementById(`ajuda-${id}`)?.scrollIntoView({ behavior: 'smooth' })

    return (
        <div className="mx-auto flex max-w-6xl gap-14 px-10 pb-32 pt-14">
            <nav className="sticky top-14 hidden h-fit w-52 shrink-0 lg:block">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Nesta página</p>
                <ul className="mt-3 space-y-1 border-l border-slate-200">
                    {SECOES.map(([id, rot]) => (
                        <li key={id}>
                            <button onClick={() => ir(id)} className="-ml-px border-l-2 border-transparent py-1 pl-4 text-left text-sm text-slate-500 hover:border-indigo-500 hover:text-slate-900">
                                {rot}
                            </button>
                        </li>
                    ))}
                </ul>
            </nav>

            <article className="min-w-0 flex-1 space-y-10">
                <header>
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600"><BookOpen className="h-5 w-5" /></div>
                    <h1 className="mt-4 text-4xl font-semibold tracking-tight text-slate-900">Como usar o Convênio 2.0</h1>
                    <p className="mt-3 max-w-2xl text-base text-slate-500">
                        Tudo o que você precisa saber para organizar os processos, extrair os dados e gerar a Análise Documental de cada convênio.
                    </p>
                </header>

                <Secao id="visao" titulo="Visão geral">
                    <p>
                        O sistema lê os PDFs da prestação de contas (inclusive páginas escaneadas), extrai os dados financeiros e documentais e monta a
                        <strong className="text-slate-800"> Análise Documental</strong> no padrão MGI/GECOV, com o Relatório de Validação, a minuta da AD
                        no modelo do Novo TCT e a planilha de Conciliação Financeira.
                    </p>
                    <p>O caminho de trabalho é sempre o mesmo:</p>
                    <Passos itens={[
                        ['Crie a pasta do convênio.', 'Ela é o destino de tudo o que for enviado daquele processo.'],
                        ['Envie os volumes para a pasta.', 'Um convênio costuma ter 3 PDFs (celebração, prestação de contas, documentos), mas pode ter quantos forem.'],
                        ['Gere a Análise Documental.', 'O sistema cruza todos os volumes da pasta, na ordem do processo.'],
                        ['Baixe as saídas e confira.', 'AD em PDF (ou Word editável) e conciliação em Excel, com os pontos a conferir destacados.'],
                    ]} />
                </Secao>

                <Secao id="pastas" titulo="Pastas de convênio">
                    <p>
                        Cada convênio tem a sua pasta. Para criar, clique em <strong className="text-slate-800">Nova pasta</strong> na barra lateral e informe o nome
                        (obrigatório), o número do convênio e o convenente (opcionais, mas ajudam na busca).
                    </p>
                    <Termos itens={[
                        ['Busca', 'O campo "Buscar convênio" na barra lateral filtra pelo nome, número ou convenente.'],
                        ['Ícone girando', 'Há volume sendo lido ou análise sendo gerada na pasta.'],
                        ['Ícone verde', 'A análise mais recente da pasta está pronta.'],
                        ['Ponto vermelho', 'Algum volume ou análise terminou com erro; abra a pasta para ver o motivo.'],
                        ['Editar', 'Muda nome, número, convenente e observação. Não afeta os dados extraídos.'],
                        ['Excluir', 'Apaga a pasta junto com os volumes, os dados extraídos e as análises dela. Não tem como desfazer.'],
                    ]} />
                    <Dica>o endereço da página acompanha a pasta e a aba abertas. Ao atualizar (F5), você continua no mesmo lugar.</Dica>
                </Secao>

                <Secao id="volumes" titulo="Enviar volumes">
                    <p>
                        Dentro da pasta, na aba <strong className="text-slate-800">Volumes</strong>, arraste os arquivos para a área de envio ou clique nela
                        para escolher. Dá para selecionar vários de uma vez. Formatos aceitos: PDF, PNG e JPG, até 100 MB por arquivo.
                    </p>
                    <Passos itens={[
                        ['Envie na ordem do processo.', 'Os volumes entram na pasta na ordem em que forem enviados (volume 1, 2, 3...).'],
                        ['Acompanhe o progresso.', 'Cada volume mostra a página que está sendo lida e uma barra de andamento.'],
                        ['Corrija a ordem se precisar.', 'Use as setas ↑ ↓ ao lado de cada volume. A análise respeita a ordem da lista.'],
                    ]} />
                    <Termos itens={[
                        ['Na fila', 'Aguardando a vez. O sistema lê um volume por vez para não pesar no computador.'],
                        ['Processando', 'Leitura (OCR) e extração em andamento. Volumes grandes levam alguns minutos; você pode continuar usando o sistema.'],
                        ['Pronto', 'Lido e gravado. Mostra páginas, resumos mensais de aplicação e lançamentos de conta corrente encontrados.'],
                        ['Erro', 'A leitura falhou (o motivo aparece embaixo do nome). Envie o arquivo de novo.'],
                    ]} />
                    <p>
                        O ícone de lixeira <strong className="text-slate-800">tira o volume da pasta</strong> sem apagar os dados: ele vai para "Arquivos sem pasta"
                        e pode ser colocado em outra pasta depois.
                    </p>
                    <Dica tipo="atencao">se o servidor for desligado no meio da leitura, o volume fica marcado como interrompido. Basta enviá-lo de novo.</Dica>
                </Secao>

                <Secao id="analise" titulo="Gerar a Análise Documental">
                    <p>
                        Quando todos os volumes estiverem <strong className="text-slate-800">Prontos</strong>, clique em
                        <strong className="text-slate-800"> Gerar análise documental</strong> (aba Volumes ou aba Análise Documental). O sistema:
                    </p>
                    <ul className="list-disc space-y-1 pl-6">
                        <li>classifica cada página (termo, plano de trabalho, extratos, notas fiscais, licitação, ofícios etc.);</li>
                        <li>monta o inventário de documentos e o checklist documental exigido pelo regime jurídico;</li>
                        <li>extrai os dados do convênio com IA e confere cada valor contra o texto do documento;</li>
                        <li>cruza notas fiscais, pagamentos, extratos, devoluções e o demonstrativo declarado;</li>
                        <li>gera o Relatório de Validação com o resultado de cada item.</li>
                    </ul>
                    <p>
                        A geração leva alguns minutos, conforme o tamanho do processo, e respeita o limite de uso da IA (Groq). Cada geração fica guardada como
                        uma <strong className="text-slate-800">versão</strong>; use "Gerar de novo" depois de incluir ou reordenar volumes e escolha a versão
                        na lista acima do resultado. Se uma geração falhar, use "Tentar de novo".
                    </p>
                </Secao>

                <Secao id="ler" titulo="Ler o resultado">
                    <p>O topo da análise mostra quantos itens tiveram cada resultado. Clique em um número para ver só aqueles itens.</p>
                    <Termos itens={[
                        ['Atende', 'Documento localizado e coerente com as regras verificadas.'],
                        ['Com ressalvas', 'Há falha formal ou divergência sem dano identificado (ex.: nota fiscal sem o número do convênio).'],
                        ['Não atende', 'Descumprimento identificado; pode gerar dano ou valor a ressarcir.'],
                        ['Não consta', 'O documento exigido não foi encontrado nos volumes da pasta.'],
                        ['Validar', 'O sistema não tem segurança para concluir (leitura duvidosa do OCR ou juízo do analista). Precisa de conferência humana.'],
                        ['Regime', 'Indica o regime jurídico identificado (Decreto 43.635/2003 ou 46.319/2013), que define o checklist e o modelo da AD.'],
                    ]} />
                    <p>
                        Na <strong className="text-slate-800">Ficha do convênio</strong>, o ícone verde indica valor confirmado no texto; o âmbar indica valor
                        que precisa ser conferido. Passe o mouse sobre o valor para ver o trecho e a página de onde ele veio.
                    </p>
                    <Termos itens={[
                        ['Itens do relatório', 'Cada item verificado, com resultado, observação e localização (documento e página).'],
                        ['Pontos de atenção', 'Possíveis danos, ressalvas, pendências documentais e questões que exigem validação, com fundamento legal e fontes.'],
                        ['Documentos', 'Checklist documental (localizado / não consta) e a matriz com todos os documentos identificados.'],
                        ['Notas fiscais', 'Notas encontradas, valores, retenções e se o pagamento correspondente foi localizado no extrato.'],
                        ['Financeiro', 'Fórmula de controle, demonstrativo declarado, devoluções, conhecimentos de receita e extratos de aplicação.'],
                    ]} />
                </Secao>

                <Secao id="saidas" titulo="Documentos de saída">
                    <p>
                        No bloco roxo <strong className="text-slate-800">Documentos de saída — Novo TCT</strong>, escolha o modelo (o sugerido vem marcado pelo
                        regime identificado) e baixe:
                    </p>
                    <Termos itens={[
                        ['Análise Documental (PDF)', 'Minuta da AD preenchida no modelo escolhido, pronta para leitura e anexação.'],
                        ['Versão editável (Word)', 'A mesma minuta em .docx, para ajustar o texto antes de finalizar.'],
                        ['Conciliação (Excel)', 'Planilha de Conciliação Financeira (GECOV/GECON) pré-preenchida.'],
                        ['Dados brutos (JSON)', 'Todo o resultado da análise, para arquivo ou integração.'],
                    ]} />
                    <Termos itens={[
                        ['Decreto 43.635/2003', 'Convênios celebrados antes da vigência do Decreto 46.319/2013.'],
                        ['Decreto 46.319/2013', 'Convênios celebrados a partir da sua vigência (com a Resolução Conjunta SEGOV/AGE 004/2015).'],
                        ['Inexecução', 'Quando o objeto não foi executado; o sistema avisa quando encontra indícios.'],
                    ]} />
                    <Dica tipo="atencao">
                        a AD é uma minuta de apoio. Trechos em amarelo na AD e células em laranja no Excel não foram confirmados no texto e devem ser conferidos
                        pelo analista antes do uso.
                    </Dica>
                </Secao>

                <Secao id="extrato" titulo="Extrato financeiro">
                    <p>
                        A aba <strong className="text-slate-800">Extrato financeiro</strong> mostra, por volume, os extratos bancários reconhecidos. Também dá
                        para abrir por "Ver extrato" na lista de volumes.
                    </p>
                    <Termos itens={[
                        ['Diagnóstico', 'Indica se a conta terminou zerada ou com saldo remanescente (e o valor).'],
                        ['Correção monetária', 'Escolha CDI (taxa anual e % do CDI, por dias úteis) ou Poupança (Selic e TR), ajuste as datas e clique em "Calcular correção". Se preferir, informe um fator manual (ex.: 1,10).'],
                        ['Regra da poupança', 'Para períodos acima de 30 dias a poupança não aplica correção, por regra definida.'],
                        ['Corrigir valores', 'Clique em qualquer valor da tabela de investimento para corrigir uma leitura errada. Depois use "Gravar correções" e confirme o antes/depois.'],
                        ['Exportar', 'Gera o parecer em PDF ou os dados em Excel com as memórias de cálculo.'],
                    ]} />
                    <p>Volumes sem extratos (ex.: celebração) não aparecem nessa aba; o texto deles continua sendo usado na Análise Documental.</p>
                </Secao>

                <Secao id="sempasta" titulo="Arquivos sem pasta">
                    <p>
                        Reúne volumes que não estão em nenhuma pasta: os enviados antes de existirem pastas e os que foram tirados de uma pasta.
                        Para organizar:
                    </p>
                    <Passos itens={[
                        ['Marque os volumes na ordem do processo.', 'O número ao lado mostra a ordem em que vão entrar.'],
                        ['Escolha a pasta de destino e clique em "Mover para a pasta",', 'ou use "Criar pasta com eles" para criar a pasta na hora.'],
                    ]} />
                    <p>Análises antigas feitas só com esses arquivos passam automaticamente para a pasta.</p>
                </Secao>

                <Secao id="limites" titulo="Cuidados e limites">
                    <ul className="list-disc space-y-2 pl-6">
                        <li>O resultado <strong className="text-slate-800">não substitui</strong> a análise do analista, da área técnica, da Controladoria ou da assessoria jurídica.</li>
                        <li>Páginas manuscritas, carimbos sobre o texto e cópias muito escuras prejudicam a leitura; esses pontos tendem a cair em "Validar".</li>
                        <li>A IA tem cota diária. Se acabar, a análise avisa e pode ser gerada de novo mais tarde.</li>
                        <li>"Limpar todos os dados", no rodapé da barra lateral, apaga pastas, volumes, extrações e análises de todo o sistema, sem volta.</li>
                    </ul>
                </Secao>

                <Secao id="faq" titulo="Perguntas frequentes">
                    <Termos itens={[
                        ['Enviei um volume na pasta errada.', 'Tire-o da pasta (lixeira) e mova-o para a pasta certa em "Arquivos sem pasta". Não precisa reenviar.'],
                        ['Esqueci um volume.', 'Envie-o para a pasta, ajuste a ordem com as setas e clique em "Gerar de novo" na Análise Documental.'],
                        ['Posso enviar o mesmo arquivo de novo?', 'Sim. Os dados antigos daquele arquivo são substituídos pela nova leitura.'],
                        ['O PDF da AD não gerou.', 'A conversão usa o Microsoft Word instalado no computador do servidor. Se ele não estiver disponível, baixe a versão editável (Word).'],
                        ['Quanto tempo demora?', 'A leitura leva em média alguns segundos por página escaneada; a análise, alguns minutos por convênio.'],
                    ]} />
                </Secao>
            </article>
        </div>
    )
}

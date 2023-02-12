import re
from urllib.parse import urljoin

import requests_cache
import logging
from bs4 import BeautifulSoup
from tqdm import tqdm
from collections import Counter

from constants import BASE_DIR, MAIN_DOC_URL, PEP_LIST_URL, EXPECTED_STATUS
from configs import configure_argument_parser, configure_logging
from outputs import control_output
from utils import get_response, find_tag


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор')]

    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})

    second_div = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})

    li_with_python = second_div.find_all('li', class_='toctree-l1')
    for li in tqdm(li_with_python):
        version_tag = li.find('a')

        href = version_tag['href']
        version_link = urljoin(whats_new_url, href)

        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, 'lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')

        results.append(
            (version_link, h1.text, dl_text)
        )

    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')

    sidebar = find_tag(soup, 'div', attrs={'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')

    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Ничего не нашлось')

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        if re.search(pattern, str(a_tag)):
            text_match = re.search(pattern, a_tag.text)
            version = text_match.group('version')
            status = text_match.group('status')
        else:
            version = a_tag.text
            status = ' '

        results.append(
            (link, version, status)
        )

    return results


def download(session):

    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    session.cache.clear()
    response = get_response(session, downloads_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')

    table = find_tag(soup, 'table', attrs={'class': 'docutils'})

    pdf_a4_tag = find_tag(table, 'a', {'href': re.compile(r'.+pdf-a4\.zip$')})
    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)

    filename = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    logging.info(f'Архив был загружен и сохранён: {archive_path}')

    response = session.get(archive_url)
    with open(archive_path, 'wb') as file:
        file.write(response.content)


def pep(session):
    accepted_status = []
    results = [('Статус', 'Количество')]

    response = get_response(session, PEP_LIST_URL)
    if response is None:
        return

    soup = BeautifulSoup(response.text, 'lxml')
    row = soup.find_all('tr')

    for link in tqdm(row):
        a_tag = link.find('a')
        symbols = link.find('abbr')
        if a_tag and symbols is not None:
            pep_link = urljoin(PEP_LIST_URL, a_tag['href'])
            status_simbol = ''
            if len(symbols.text) > 1:
                status_simbol = symbols.text[-1]
            response = get_response(session, pep_link)
            if response is None:
                continue
            soup = BeautifulSoup(response.text, 'lxml')
            dl_tag = soup.find('dl')
            dt_tag = dl_tag.find_all('dt')
            for dt in dt_tag:
                if dt.text == 'Status:':
                    status = dt.find_next_sibling('dd')
                    try:
                        if status.text in EXPECTED_STATUS[status_simbol]:
                            accepted_status.append(status.text)
                    except KeyError as err:
                        logging.error(f'Возникла ошибка: {err},'
                                      f'неопозданный статус - {status_simbol}')

    counter = dict(Counter(accepted_status))
    results.extend((counter.items()))

    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')

    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')

    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)
    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()

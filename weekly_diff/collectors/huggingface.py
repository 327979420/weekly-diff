"""Recent trending and configured organization models from Hugging Face."""
from datetime import datetime, timedelta

from weekly_diff.collectors import in_window, valid_url
from weekly_diff.config import Config
from weekly_diff.http import Http
from weekly_diff.models import Candidate
from weekly_diff.text import parse_date


def collect(cfg: Config, window: tuple[datetime, datetime], http: Http) -> list[Candidate]:
    settings = cfg.sources.huggingface
    requests = [({'sort': 'trendingScore', 'limit': settings.trending_limit},
                 (window[1] - timedelta(days=settings.created_within_days), window[1]))]
    requests.extend(({'author': org, 'sort': 'createdAt', 'limit': settings.org_limit}, window)
                    for org in settings.orgs)
    result = {}
    for params, period in requests:
        try:
            models = http.get_json(settings.api_url, params={**params, 'direction': -1, 'full': 'true'})
            for model in models:
                date = parse_date(model.get('createdAt'))
                if not in_window(date, period):
                    continue
                name = model['id']
                url = f'{settings.base_url}/{name}'
                if not valid_url(url):
                    continue
                signals = {key: model[key] for key in ('likes', 'downloads') if model.get(key) is not None}
                if model.get('trendingScore') is not None:
                    signals['trending_score'] = model['trendingScore']
                candidate = Candidate(f'hf:{name}', name, url, settings.name, 'huggingface',
                                      date, name, True, 'models', signals,
                                      {'pipeline_tag': model.get('pipeline_tag'),
                                       'author': model.get('author') or name.partition('/')[0]})
                if name in result:
                    result[name].signals.update(signals)
                else:
                    result[name] = candidate
        except Exception as error:
            http.failure(f"{settings.name} {params.get('author', params['sort'])}", error)
    return list(result.values())

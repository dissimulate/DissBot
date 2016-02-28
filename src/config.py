import ujson

class Config():
    filename = ''

    _data = {}

    def __init__(self, filename):
        self.filename = filename

    def load(self):
        with open(self.filename, 'r') as fp:
            self._data = ujson.load(fp)

    def save(self):
        with open(self.filename, 'w') as fp:
            ujson.dump(self._data, fp, indent=4, sort_keys=True)

    def get(self, keys, default=[]):
        if not isinstance(keys, list):
            keys = [keys]

        last = self._data

        for key in keys[:-1]:
            last.get(key, {})
            last = last[key]

        return last.get(keys[-1], default)

    def getd(self, key, default=[]):
        self._data.setdefault(key, default)
        self.save()
        return self.get(key)

    def append(self, keys, thing):
        self.get(keys, []).append(thing)
        self.save()

    def remove(self, keys, thing):
        val = self.get(keys, [])
        if thing in val:
            val.remove(thing)
        self.save()

    def set(self, keys, value):
        if not isinstance(keys, list):
            keys = [keys]

        last = self._data

        for key in keys[:-1]:
            last.setdefault(key, {})
            last = last[key]

        last[keys[-1]] = value
        self.save()

    def delete(self, keys):
        if not isinstance(keys, list):
            keys = [keys]

        last = self._data

        for key in keys[:-1]:
            last.setdefault(key, {})
            last = last[key]

        del last[keys[-1]]
        self.save()

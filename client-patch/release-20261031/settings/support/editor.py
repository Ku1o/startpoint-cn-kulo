"""Narrow R11Editor surface extracted from the tested capabilities adapter.
No feature-group loading, archive scan, historical main, packaging or slot additions.
"""
import copy, hashlib
import bootstrap, bodies, framework
from swfabc import SwfAbc

def digest(raw): return hashlib.sha256(raw).hexdigest()
def body_bytes(body):
    fmt = framework.FMT
    writer = fmt.W()
    for value in body[:5]: writer.u30(value)
    writer.u30(len(body[5])); writer.raw(body[5]); writer.u30(len(body[6]))
    for handler in body[6]:
        for value in handler: writer.u30(value)
    writer.u30(len(body[7]))
    for trait in body[7]: fmt.write_trait(writer, trait)
    return writer.out()

class R11Editor(framework.Editor):
    def __init__(self, source):
        super().__init__(source, locks={})
        self.contract = {}
        self.added_state = []
    def body(self, label):
        body = super().body(label)
        if label not in self.contract:
            self.contract[label] = {'sha': digest(body[5]), 'header': list(body[1:5]),
                                    'body': bodies.resolve(self.abc, label), 'method': body[0]}
            self.locks.setdefault(label, dict(self.contract[label]))
        return body
    def number(self, value): return super().number(value)
    def add_slot(self, *args, **kwargs):
        raise ValueError('Settings may not add instance/static storage slots')

def compose(editor): return editor.swf.serialize()

export const languages = {
    config: [
        'yaml',
        'json',
        'toml',
        'xml',
        'ini'
    ],
    code: [
        'javascript',
        'typescript',
        'python',
        'java',
        'kotlin',
        'cpp',
        'csharp',
        'shell',
        'ruby',
        'rust',
        'sql',
        'go',
    ],
    web: [
        'html',
        'css',
        'php'
    ],
    misc: [
        'plain',
        'dockerfile',
        'markdown',
        'railway'
    ],
    custom: [
        'properties',
        'log',
        'javastacktrace',
        'groovy',
        'haskell',
        'protobuf',
        'brainfuck'
    ]
};

export const languageIds = Object.values(languages).flat(1);

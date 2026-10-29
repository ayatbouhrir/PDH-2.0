import { readFileSync } from 'fs';

import resolve from '@rollup/plugin-node-resolve';
import typescript from '@rollup/plugin-typescript';
import { terser } from 'rollup-plugin-terser';
import dts from 'rollup-plugin-dts';
import pkg from './package.json';
const extensions = ['.js', '.ts'];

const copyright = readFileSync('./LICENSE', 'utf-8')
  .split(/\n/g)
  .filter((line) => /^Copyright\s+/.test(line))
  .map((line) => line.replace(/^Copyright\s+/, ''))
  .join(', ');

const options = {
  input: 'src/index.ts',
  plugins: [
    resolve({ extensions }), // so Rollup can find `ms`
    typescript({ tsconfig: './tsconfig.json' }),
  ],
};

export default [
  // browser-friendly UMD build
  {
    ...options,
    plugins: [
      ...options.plugins,
      terser({
        output: {
          preamble: `// ${pkg.homepage} v${pkg.version} Copyright ${copyright}`,
        },
      }),
    ],
    output: [
      {
        name: pkg.name,
        file: `dist/index.min.js`,
        format: 'umd',
        exports: 'named',
      },
      {
        file: pkg.browser,
        format: 'cjs',
        exports: 'named',
      },
    ],
  },
  // CommonJS (for Node) and ES module (for bundlers) build.
  // (We could have three entries in the configuration array
  // instead of two, but it's quicker to generate multiple
  // builds from a single configuration where possible, using
  // an array for the `output` option, where we can specify
  // `file` and `format` for each target)
  {
    ...options,
    external: ['rbush'],
    plugins: [...options.plugins],
    output: [
      {
        file: pkg.module,
        format: 'es',
        exports: 'named',
        banner: `// ${pkg.homepage} v${pkg.version} Copyright ${copyright}`,
      },
    ],
  },
  {
    // path to your declaration files root
    input: './dist/types/index.d.ts',
    output: [{ file: 'dist/index.d.ts', format: 'es' }],
    plugins: [dts()],
  },
];

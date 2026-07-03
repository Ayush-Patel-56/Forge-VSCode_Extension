// webpack.config.js
'use strict';
const path = require('path');
const webpack = require('webpack');

const extensionConfig = {
  target: 'node',
  mode: 'none',
  entry: './src/extension.ts',
  output: {
    path: path.resolve(__dirname, 'out'),
    filename: 'extension.js',
    libraryTarget: 'commonjs2',
  },
  externals: { vscode: 'commonjs vscode' },
  resolve: { extensions: ['.ts', '.js'] },
  module: { rules: [{ test: /\.ts$/, loader: 'ts-loader' }] },
  devtool: 'nosources-source-map',
};

const chatWebviewConfig = {
  target: 'web',
  mode: 'none',
  entry: './webview-src/chat/index.tsx',
  output: {
    path: path.resolve(__dirname, 'out', 'webview'),
    filename: 'chat.js',
  },
  resolve: { extensions: ['.tsx', '.ts', '.js'] },
  module: {
    rules: [
      { test: /\.tsx?$/, loader: 'ts-loader', options: { configFile: path.resolve(__dirname, 'webview-src', 'tsconfig.json') } },
      { test: /\.css$/, use: ['style-loader', 'css-loader', 'postcss-loader'] },
    ],
  },
  plugins: [
    new webpack.DefinePlugin({ 'process.env.NODE_ENV': JSON.stringify('production') }),
  ],
  devtool: 'nosources-source-map',
};

const mcpWebviewConfig = {
  ...chatWebviewConfig,
  entry: './webview-src/mcp/index.tsx',
  output: {
    path: path.resolve(__dirname, 'out', 'webview'),
    filename: 'mcp.js',
  },
};

module.exports = [extensionConfig, chatWebviewConfig, mcpWebviewConfig];

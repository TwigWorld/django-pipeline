from pipeline.compilers import CompilerBase

class HtmlCompiler(CompilerBase):
  output_extension = 'html'

  def match_file(self, filename):
    return filename.endswith('.html')

  def compile_file(self, infile, outfile, outdated=False, force=False):
    if not outdated and not force:
      return  # No need to recompiled file
    return self.compile(infile, outfile)
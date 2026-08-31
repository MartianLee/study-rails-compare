class ApplicationController < ActionController::API
  PER_PAGE = 20
  EXCERPT  = 160

  private

  def page_param
    [params[:page].to_i, 1].max
  end

  def iso(time)
    time&.utc&.strftime("%Y-%m-%dT%H:%M:%SZ")
  end
end
